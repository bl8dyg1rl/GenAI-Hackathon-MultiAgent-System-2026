"""Scout Intent implementation for this application, following Meterless' agnostic spec.

This is a Python implementation of the public Scout concepts (Sense, Interpret,
Guard, Route, Recommend, signed execution contract), not the official engine's
conformance-tested distribution. It is deterministic, local, and model-free;
all actual LLM inference occurs through Meterless Nightshift elsewhere.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

REGISTRY_VERSION = 1
POLICY_PACK_VERSION = "colombia-readonly-v1"
CONTRACT_TTL_MINUTES = 5

# Each intent has mandatory examples to support repeatable classification/evaluation.
INTENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "research.dataset_discovery", "category": "research",
        "description": "Discover official public datasets and their metadata.", "riskClass": "low",
        "triggers": ("datasets", "dataset", "conjunto de datos", "datos disponibles", "fuentes de datos",
                     "buscar datos", "busca datos", "catalogo", "catálogo", "que datos", "qué datos", "datos abiertos"),
        "examples": ("Busca datos de desempleo", "Qué datasets hay sobre pobreza en Colombia"),
    },
    {
        "id": "research.indicator_analysis", "category": "research",
        "description": "Query or analyze public indicators in time, including economic indicators.", "riskClass": "low",
        "triggers": ("inflacion", "inflación", "desempleo", "pib", "producto interno bruto", "crecimiento economico",
                     "crecimiento económico", "tasa de cambio", "trm", "tasa de interes", "tasa de interés",
                     "indicador", "serie historica", "serie histórica", "cómo ha cambiado", "como ha cambiado", "cómo cambió", "como cambio", "cambió", "cambio",
                     "comparar", "relacion entre", "relación entre", "estadisticas", "estadísticas", "tendencia"),
        "examples": ("Cómo cambió el desempleo en Colombia", "Compara inflación y TRM"),
    },
    {
        "id": "research.regional_comparison", "category": "research",
        "description": "Compare public statistics across departments or municipalities.", "riskClass": "low",
        "triggers": ("departamento", "departamentos", "municipio", "municipios", "por region", "por región",
                     "regional", "comparacion regional", "comparación regional", "entre ciudades", "por ciudad"),
        "examples": ("Compara pobreza por departamento", "Desempleo entre ciudades colombianas"),
    },
    {
        "id": "general.question", "category": "general",
        "description": "A safe general question that does not need a data tool.", "riskClass": "low",
        "triggers": (), "examples": ("Hola", "Explícame qué es la inflación"),
    },
)

INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"reveal\s+(the\s+)?(system prompt|secrets|runtime token|api key|credentials)",
    r"\b(show|print|dump|exfiltrate)\b.{0,40}\b(token|api key|credentials|secret)\b",
    r"</?system\b", r"\[INST\]", r"developer message",
    r"\b(drop|truncate|delete\s+from|update\s+\w+\s+set|insert\s+into)\b",
    r"disable\s+(the\s+)?(guard|safety|security)",
)

INTENT_CAPABILITIES: dict[str, list[str]] = {
    "research.dataset_discovery": ["meterless.chat", "catalog.search", "zetaris.inspect", "zetaris.query", "agent.message", "audit.review", "response.compose"],
    "research.indicator_analysis": ["meterless.chat", "catalog.search", "zetaris.inspect", "zetaris.query", "agent.message", "audit.review", "response.compose"],
    "research.regional_comparison": ["meterless.chat", "catalog.search", "zetaris.inspect", "zetaris.query", "agent.message", "audit.review", "response.compose"],
    "general.question": ["meterless.chat", "agent.message", "response.compose"],
}


@dataclass
class ScoutDecision:
    trace_id: str
    intent: str
    confidence: float
    candidates: list[dict[str, Any]]
    risk: dict[str, Any]
    clarification: str | None
    tool_plan: list[dict[str, str]]
    execution_contract: dict[str, Any] | None
    stages: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id, "intent": self.intent, "confidence": self.confidence,
            "candidates": self.candidates, "risk": self.risk, "clarification": self.clarification,
            "tool_plan": self.tool_plan, "execution_contract": self.execution_contract,
            "stages": self.stages,
        }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _secret() -> bytes:
    value = os.getenv("SCOUT_SIGNING_SECRET", "local-development-secret-change-this")
    return value.encode("utf-8")


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sign(contract: dict[str, Any]) -> dict[str, Any]:
    unsigned = {k: v for k, v in contract.items() if k != "signature"}
    signed = dict(unsigned)
    signed["signature"] = hmac.new(_secret(), _canonical(unsigned), hashlib.sha256).hexdigest()
    return signed


def verify_contract_signature(contract: dict[str, Any] | None) -> bool:
    """Verify authenticity without considering TTL, for safe expiry-only replanning."""
    if not isinstance(contract, dict) or contract.get("signedBy") != "scout":
        return False
    signature = contract.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    unsigned = {k: v for k, v in contract.items() if k != "signature"}
    expected = hmac.new(_secret(), _canonical(unsigned), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def verify_contract(contract: dict[str, Any] | None, *, now: datetime | None = None) -> bool:
    """Verify signature, expiry, and the required contract shape at every tool boundary."""
    if not isinstance(contract, dict) or contract.get("signedBy") != "scout":
        return False
    if not verify_contract_signature(contract):
        return False
    try:
        expires = datetime.fromisoformat(str(contract["expiresAt"]).replace("Z", "+00:00"))
        issued = datetime.fromisoformat(str(contract["issuedAt"]).replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError):
        return False
    clock = now or _utcnow()
    if issued > clock + timedelta(seconds=5) or clock >= expires or expires <= issued:
        return False
    scope = contract.get("scope")
    if not isinstance(scope, dict) or not isinstance(scope.get("capabilities"), list):
        return False
    return isinstance(contract.get("toolPlan"), list) and isinstance(contract.get("traceId"), str)


def require_capability(contract: dict[str, Any] | None, capability: str) -> None:
    if not verify_contract(contract):
        raise PermissionError("El contrato Scout es inválido o expiró; no se ejecutó la herramienta.")
    if capability not in contract.get("scope", {}).get("capabilities", []):
        raise PermissionError(f"El contrato Scout no autoriza la capacidad {capability}.")


def _score(prompt: str, intent: dict[str, Any]) -> tuple[float, list[str]]:
    normalized = re.sub(r"\s+", " ", prompt.casefold())
    matches = [trigger for trigger in intent["triggers"] if trigger in normalized]
    # A transparent deterministic score: one specific trigger usually yields >=0.40;
    # repeated independent cues move it toward high confidence.
    weight = sum(1.25 if len(trigger) >= 11 else 0.9 for trigger in matches)
    score = min(0.99, weight / (weight + 1.25)) if weight else 0.0
    return score, matches


def _guard(prompt: str) -> dict[str, Any]:
    matched = [pattern for pattern in INJECTION_PATTERNS if re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)]
    if matched:
        return {"level": "block", "flags": ["prompt_injection_or_write_request"],
                "redactions": [], "reason": "La petición intenta anular salvaguardas, revelar secretos o ejecutar una operación de escritura."}
    return {"level": "low", "flags": [], "redactions": [], "reason": None}


def _route(intent_id: str) -> list[dict[str, str]]:
    by_intent = {
        "research.dataset_discovery": [("catalog.search", "Descubrir metadatos públicos"), ("zetaris.inspect", "Inspeccionar tablas permitidas"), ("zetaris.query", "Consultar datos federados")],
        "research.indicator_analysis": [("catalog.search", "Descubrir fuentes relevantes"), ("zetaris.inspect", "Inspeccionar esquemas"), ("zetaris.query", "Consultar indicadores mediante Zetaris")],
        "research.regional_comparison": [("catalog.search", "Descubrir datos regionales"), ("zetaris.inspect", "Inspeccionar esquemas"), ("zetaris.query", "Consultar datos regionales mediante Zetaris")],
        "general.question": [],
    }
    plan = [{"tool": tool, "purpose": purpose} for tool, purpose in by_intent.get(intent_id, [])]
    plan.append({"tool": "meterless.chat", "purpose": "Inferencia de agentes y composición de respuesta usando Nightshift"})
    return plan


class ScoutIntent:
    """Deterministic intent/risk/router engine that signs short-lived execution contracts."""

    def decide(self, prompt: str, *, surface: str = "chat", user: str = "local-user") -> ScoutDecision:
        trace_id = str(uuid.uuid4())
        candidates: list[dict[str, Any]] = []
        # Sense: score the full small registry, not just a hand-picked winner.
        for spec in INTENTS:
            score, matched = _score(prompt, spec)
            candidates.append({"intent": spec["id"], "score": round(score, 3), "matched_triggers": matched})
        candidates.sort(key=lambda item: item["score"], reverse=True)
        winner = candidates[0]
        if winner["score"] == 0:
            winner = {"intent": "general.question", "score": 0.35, "matched_triggers": []}
            candidates = [winner] + [c for c in candidates if c["intent"] != "general.question"]
        confidence = float(winner["score"])
        risk = _guard(prompt)
        stages = ["sense", "interpret", "guard"]
        clarification = None
        if risk["level"] == "block":
            return ScoutDecision(trace_id, winner["intent"], confidence, candidates[:3], risk,
                                 None, [], None, stages + ["route_refused"])

        if winner["intent"] != "general.question" and 0.40 <= confidence < 0.55:
            clarification = "¿Qué indicador, periodo o región te interesa? Con un poco más de precisión podré buscar la fuente adecuada."
        stages.append("route")
        tool_plan = _route(winner["intent"])
        stages.append("recommend")
        now = _utcnow()
        capabilities = INTENT_CAPABILITIES[winner["intent"]]
        contract = {
            "contractId": str(uuid.uuid4()), "traceId": trace_id, "parentId": None,
            "intent": {"primary": winner["intent"], "parameters": {"prompt": prompt[:2000]},
                       "references": {}, "confidence": confidence, "alternates": candidates[1:3]},
            "risk": risk, "toolPlan": tool_plan,
            "modelProfile": {"provider": "meterless", "mode": "configured-meterless-routing-mode"},
            "scope": {"user": user[:100], "surface": surface[:80], "capabilities": capabilities,
                      "deadline": (now + timedelta(minutes=CONTRACT_TTL_MINUTES)).isoformat()},
            "issuedAt": now.isoformat(), "expiresAt": (now + timedelta(minutes=CONTRACT_TTL_MINUTES)).isoformat(),
            "registryVersion": REGISTRY_VERSION, "policyPackVersion": POLICY_PACK_VERSION,
            "signedBy": "scout",
        }
        contract = _sign(contract)
        return ScoutDecision(trace_id, winner["intent"], confidence, candidates[:3], risk,
                             clarification, tool_plan, contract, stages)

    def replan(self, parent: dict[str, Any], *, reason: str) -> dict[str, Any]:
        """Issue a new short-lived contract with lineage after expiry/failure."""
        if not isinstance(parent, dict) or parent.get("signedBy") != "scout":
            raise PermissionError("No se puede replanificar sin un contrato Scout anterior.")
        now = _utcnow()
        new_contract = {k: v for k, v in parent.items() if k not in {"signature", "contractId", "parentId", "issuedAt", "expiresAt"}}
        new_contract["contractId"] = str(uuid.uuid4())
        new_contract["parentId"] = parent.get("contractId")
        new_contract["issuedAt"] = now.isoformat()
        new_contract["expiresAt"] = (now + timedelta(minutes=CONTRACT_TTL_MINUTES)).isoformat()
        new_contract["replanReason"] = reason[:300]
        return _sign(new_contract)
