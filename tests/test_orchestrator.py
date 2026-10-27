import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from python_app.meterless import MeterlessConfig
from python_app.orchestrator import ChatOrchestrator
from python_app.state_store import StateStore
from python_app.zetaris import ZetarisConfig


class FakeRuntime:
    def __init__(self):
        self.config = SimpleNamespace(routing_mode="meterless/auto")
        self.calls = []

    def chat(self, messages):
        system = messages[0]["content"]
        self.calls.append(system)
        if "Eres Data Scout" in system:
            answer = {"search_query": "desempleo Colombia", "reason": "Búsqueda de metadatos"}
        elif "Eres Query & Stats Analyst" in system:
            answer = {"sql": "SELECT anio, tasa FROM COLOMBIA_STATS.desempleo LIMIT 10",
                      "selected_table": "COLOMBIA_STATS.desempleo", "purpose": "Consultar serie", "explain_reason": ""}
        elif "Eres Evidence Auditor" in system:
            answer = {"status": "verified", "grounded": True, "issues": [], "request_retry": False,
                      "retry_instruction": "", "limitations": []}
        elif "Eres Answer Composer" in system:
            return {"answer": "La consulta devolvió dos filas de la tabla registrada en Zetaris.", "model": "meterless/auto", "provider": "meterless"}
        else:
            raise AssertionError("Se intentó una llamada de modelo sin el adaptador esperado")
        return {"answer": json.dumps(answer, ensure_ascii=False), "model": "meterless/auto", "provider": "meterless"}


class FakeZetaris:
    def __init__(self, config):
        self.config = config
        self.queries = []

    def preview_table(self, table, limit=3):
        return {"ok": True, "source": "Zetaris", "sql": f"SELECT * FROM {table} LIMIT {limit}",
                "headers": ["anio", "tasa"], "rows": [{"anio": 2023, "tasa": 10.5}], "row_count": 1}

    def query(self, sql, page_limit=100):
        self.queries.append(sql)
        return {"ok": True, "source": "Zetaris", "sql": sql, "headers": ["anio", "tasa"],
                "rows": [{"anio": 2023, "tasa": 10.5}, {"anio": 2024, "tasa": 9.7}], "row_count": 2, "page_limit": page_limit}


def fake_catalog(query, limit=5):
    return {"source": "datos_abiertos", "query": query, "error": None,
            "results": [{"id": "abcd-1234", "name": "Estadísticas de desempleo", "description": "Metadatos oficiales",
                         "link": "https://www.datos.gov.co/d/abcd-1234", "updated_at": "2025-01-01", "source": "Datos Abiertos Colombia"}]}


class OrchestratorTests(unittest.TestCase):
    def test_four_agents_collaborate_and_queries_use_zetaris(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(os.path.join(tmp, "events.sqlite3"))
            runtime = FakeRuntime()
            zetaris_config = ZetarisConfig(token="test-id-token", allowed_tables=["COLOMBIA_STATS.desempleo"],
                                           table_map={"abcd-1234": "COLOMBIA_STATS.desempleo"})
            fake_zetaris = FakeZetaris(zetaris_config)
            result = ChatOrchestrator(
                meterless_config=MeterlessConfig(token="test-meterless-token"),
                zetaris_config=zetaris_config, store=store,
                meterless_client=runtime, zetaris_client=fake_zetaris, catalog_search=fake_catalog,
            ).run("¿Cómo cambió el desempleo de Colombia en 2023 y 2024?")
            self.assertEqual(result["status"], "completed")
            self.assertIn("Zetaris", result["answer"])
            self.assertEqual(fake_zetaris.queries, ["SELECT anio, tasa FROM COLOMBIA_STATS.desempleo LIMIT 10"])
            agents = {event["agent"] for event in store.list_events(result["run_id"])}
            self.assertTrue({"DataScout", "QueryStatsAnalyst", "EvidenceAuditor", "AnswerComposer", "ScoutIntent"}.issubset(agents))
            types = {event["event_type"] for event in store.list_events(result["run_id"])}
            self.assertIn("agent.message.sent", types)
            self.assertIn("agent.message.received", types)
            self.assertIn("model.request", types)
            self.assertIn("model.response", types)
            self.assertEqual(len(runtime.calls), 4)


if __name__ == "__main__":
    unittest.main()
