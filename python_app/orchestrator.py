"""Coordinator for a collaborative, bounded multi-agent run."""
from __future__ import annotations

import concurrent.futures
import json
import uuid
from typing import Any, Callable

from .agents import (AnswerComposerAgent, DataScoutAgent, EvidenceAuditorAgent,
                     ModelGateway, QueryStatsAnalystAgent, SharedWorkspace)
from .meterless import MeterlessClient, MeterlessConfig, MeterlessError
from .scout_intent import ScoutIntent
from .state_store import StateStore
from .zetaris import ZetarisClient, ZetarisConfig
from .sources import search_datos_abiertos


class ChatOrchestrator:
    def __init__(self, *, meterless_config: MeterlessConfig, zetaris_config: ZetarisConfig,
                 store: StateStore, meterless_client: MeterlessClient | None = None,
                 zetaris_client: ZetarisClient | None = None,
                 catalog_search: Callable[..., dict[str, Any]] | None = None):
        self.meterless_config = meterless_config
        self.zetaris_config = zetaris_config
        self.store = store
        self.meterless_client = meterless_client or MeterlessClient(meterless_config)
        self.zetaris_client = zetaris_client or ZetarisClient(zetaris_config)
        self.catalog_search = catalog_search
        self.scout = ScoutIntent()

    def run(self, question: str, *, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        decision = self.scout.decide(question, surface="chat", user="local-user")
        run_id = str(uuid.uuid4())
        self.store.create_run(run_id, decision.trace_id, question, decision.intent, decision.confidence)
        self.store.log_event(run_id, "ScoutIntent", "scout.decision", "Scout completó Sense → Interpret → Guard → Route → Recommend.",
                             {"decision": decision.as_dict()}, success=True)
        if decision.risk["level"] == "block":
            answer = "No ejecuté herramientas: la solicitud activó el control de seguridad de Scout Intent. Reformula la pregunta sin pedir secretos ni operaciones de escritura."
            self.store.log_event(run_id, "ScoutIntent", "contract.refused", "Solicitud bloqueada antes de ejecutar herramientas.", decision.risk, success=False)
            result = self._result(run_id, decision, answer, status="blocked", evidence={}, audit=None, limitations=[decision.risk.get("reason") or "Solicitud bloqueada."])
            self.store.finish_run(run_id, status="blocked", answer=answer, summary=result)
            return result
        if decision.clarification:
            answer = decision.clarification
            self.store.log_event(run_id, "ScoutIntent", "clarification.requested", "Scout solicitó aclaración antes de consultar fuentes.", {"clarification": answer}, success=True)
            result = self._result(run_id, decision, answer, status="needs_clarification", evidence={}, audit=None, limitations=[])
            self.store.finish_run(run_id, status="needs_clarification", answer=answer, summary=result)
            return result
        if not self.meterless_config.token.strip() or self.meterless_config.token.strip() == "rt-local":
            answer = "El enrutamiento local de Scout funciona, pero falta un Runtime token real. Abre Ajustes, configura Meterless Nightshift y prueba la conexión antes de usar los agentes."
            self.store.log_event(run_id, "System", "configuration.required", "El token de Nightshift no está configurado; no se hicieron llamadas a modelos.", {"provider": "meterless"}, success=False)
            result = self._result(run_id, decision, answer, status="configuration_required", evidence={}, audit=None, limitations=["Todas las llamadas de modelo requieren Meterless Nightshift; no hay proveedor alternativo."])
            self.store.finish_run(run_id, status="configuration_required", answer=answer, summary=result)
            return result
        if not decision.execution_contract:
            answer = "Scout no emitió un contrato de ejecución; se rechazó la tarea por seguridad."
            result = self._result(run_id, decision, answer, status="blocked", evidence={}, audit=None, limitations=[answer])
            self.store.finish_run(run_id, status="blocked", answer=answer, summary=result)
            return result

        workspace = SharedWorkspace(run_id, decision.trace_id, decision.execution_contract, self.store, self.scout)
        gateway = ModelGateway(self.meterless_client, workspace, self.store)
        data_scout = DataScoutAgent(workspace, gateway, self.store, self.zetaris_config.table_map,
                                    self.zetaris_config.allowed_tables, catalog_search=self.catalog_search or search_datos_abiertos)
        analyst = QueryStatsAnalystAgent(workspace, gateway, self.store, self.zetaris_client)
        auditor = EvidenceAuditorAgent("EvidenceAuditor", workspace, gateway, self.store)
        composer = AnswerComposerAgent("AnswerComposer", workspace, gateway, self.store)
        limitations: list[str] = []

        if decision.intent == "general.question":
            # GENERAL stays within the safe model capability and does not call data tools.
            discovery = {"query": "", "candidates": [], "error": None}
            query_result = {"ok": False, "executed": False, "sql": None, "selected_table": None,
                            "headers": [], "rows": [], "row_count": 0, "error": None, "source": "Zetaris"}
            audit = {"status": "insufficient", "grounded": False, "issues": ["No se consultaron fuentes de datos para esta pregunta general."],
                     "request_retry": False, "retry_instruction": "", "limitations": ["No se ejecutó una consulta estadística."]}
            try:
                answer = composer.compose(question, discovery, query_result, audit,
                                          ["Pregunta general: no se consultaron datos de Zetaris."], history=history)
                result = self._result(run_id, decision, answer, status="completed", evidence={"catalog_candidates": [], "query": _public_query_result(query_result), "audit": audit}, audit=audit,
                                      limitations=["Pregunta general: no se consultaron datos de Zetaris."])
                self.store.finish_run(run_id, status="completed", answer=answer, summary=result)
                return result
            except MeterlessError as exc:
                answer = f"No se pudo completar la respuesta con Meterless Nightshift: {str(exc)}"
                result = self._result(run_id, decision, answer, status="provider_error", evidence={}, audit=None, limitations=[])
                self.store.finish_run(run_id, status="provider_error", answer=answer, summary=result)
                return result

        # Real collaboration, not a sequential chain: metadata discovery and Zetaris schema
        # inspection start together. Their results are then exchanged on the persistent bus.
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="cdi-agent") as executor:
                scout_future = executor.submit(data_scout.discover, question)
                schema_future = executor.submit(analyst.inspect_tables)
                discovery = scout_future.result()
                schemas = schema_future.result()

            data_scout.receive_schema_feedback()
            workspace.send("Orchestrator", "QueryStatsAnalyst", "shared_workspace_context", {
                "question": question, "catalog_candidates": discovery.get("candidates", []),
                "note": "Los candidatos son metadatos; solo una tabla registrada y permitida en Zetaris puede aportar filas.",
            })
            workspace.send("Orchestrator", "DataScout", "shared_workspace_context", {
                "question": question, "zetaris_schemas": [{"table": s["table"], "headers": s["headers"], "available": s["available"]} for s in schemas],
            })
            # Let both agents receive and log their peer's contribution before planning queries.
            analyst.receive_messages()
            data_scout.receive_schema_feedback()

            if discovery.get("error"):
                limitations.append(str(discovery["error"]))
            if not schemas or not any(s.get("available") for s in schemas):
                limitations.append("No hay una tabla consultable en Zetaris. Registra una fuente de estadísticas y configura su nombre exacto en ZETARIS_TABLES.")

            query_result = analyst.plan_and_query(question, discovery, schemas)
            audit = auditor.review(question, discovery, schemas, query_result)
            # Bounded collaboration loop: auditor may ask Analyst to correct one query once.
            if audit.get("request_retry") and query_result.get("selected_table"):
                corrected = analyst.plan_and_query(question, discovery, schemas,
                    correction=audit.get("retry_instruction") or "Revisa la consulta anterior y devuelve una consulta más amplia de solo lectura.")
                if corrected.get("executed"):
                    query_result = corrected
                    audit = auditor.review(question, discovery, schemas, query_result)
                    limitations.append("El Auditor solicitó y revisó una única corrección de consulta.")

            if discovery.get("error"):
                limitations.append(str(discovery["error"]))
            if query_result.get("error"):
                limitations.append(str(query_result["error"]))
            limitations.extend(str(x) for x in audit.get("limitations", []) if x)
            if not query_result.get("rows"):
                limitations.append("Los resultados del catálogo son metadatos candidatos; todavía no hay filas estadísticas verificadas de Zetaris.")
            answer = composer.compose(question, discovery, query_result, audit, _dedupe(limitations), history=history)
            evidence = {"catalog_candidates": discovery.get("candidates", []), "query": _public_query_result(query_result),
                        "audit": audit}
            result = self._result(run_id, decision, answer, status="completed", evidence=evidence,
                                  audit=audit, limitations=_dedupe(limitations))
            self.store.log_event(run_id, "Orchestrator", "run.completed", "Finalizó el trabajo multiagente.",
                                 {"status": result["status"], "catalog_candidates": len(discovery.get("candidates", [])),
                                  "query_executed": query_result.get("executed", False), "row_count": query_result.get("row_count", 0),
                                  "audit_status": audit.get("status")}, success=True)
            self.store.finish_run(run_id, status="completed", answer=answer, summary=result)
            return result
        except MeterlessError as exc:
            answer = f"No se pudo completar la tarea porque Meterless Nightshift no respondió correctamente: {str(exc)}"
            self.store.log_event(run_id, "Orchestrator", "run.failed", "Se detuvo la tarea al fallar Meterless; no se usó un proveedor alternativo.",
                                 {"error": str(exc)}, success=False)
            result = self._result(run_id, decision, answer, status="provider_error", evidence={}, audit=None,
                                  limitations=["No se usó ningún proveedor de IA alternativo."])
            self.store.finish_run(run_id, status="provider_error", answer=answer, summary=result)
            return result
        except Exception as exc:
            # The user receives a safe operational failure; detail is retained locally without credentials.
            answer = f"La ejecución multiagente falló en {type(exc).__name__}. Revisa la pestaña Actividad para localizar el paso que falló."
            self.store.log_event(run_id, "Orchestrator", "run.failed", answer,
                                 {"error_type": type(exc).__name__, "error": str(exc)[:500]}, success=False)
            result = self._result(run_id, decision, answer, status="failed", evidence={}, audit=None,
                                  limitations=["No se presentaron cifras como resultado de una ejecución fallida."])
            self.store.finish_run(run_id, status="failed", answer=answer, summary=result)
            return result

    def _result(self, run_id: str, decision: Any, answer: str, *, status: str,
                evidence: dict[str, Any], audit: dict[str, Any] | None, limitations: list[str]) -> dict[str, Any]:
        events = self.store.list_events(run_id)
        messages = self.store.list_messages(run_id)
        return {
            "answer": answer, "run_id": run_id, "trace_id": decision.trace_id,
            "intent": decision.intent, "confidence": decision.confidence, "status": status,
            "provider": "meterless", "model": self.meterless_config.routing_mode,
            "evidence": evidence, "audit": audit, "limitations": _dedupe(limitations),
            "activity": [{"id": e["id"], "agent": e["agent"], "event_type": e["event_type"],
                          "summary": e["summary"], "success": e["success"], "duration_ms": e["duration_ms"]}
                         for e in events],
            "agent_messages": [{"id": m["id"], "sender": m["sender"], "recipient": m["recipient"],
                                "message_type": m["message_type"], "delivered": m["delivered"]} for m in messages],
        }


def _public_query_result(result: dict[str, Any]) -> dict[str, Any]:
    return {k: result.get(k) for k in ("ok", "executed", "sql", "selected_table", "headers", "rows", "row_count", "source", "error", "purpose")}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output
