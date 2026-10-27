"""Meterless Nightshift provider adapter (OpenAI-compatible text API).

All LLM requests in this application go through this adapter. Tokens are never
included in logs or error messages.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import urlparse

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"
DEFAULT_ROUTING_MODE = "meterless/auto"
APP_ID = "colombia-data-intelligence"
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_MODES = (
    "meterless/auto", "meterless/fast", "meterless/deep", "meterless/cheap",
    "meterless/local", "meterless/fusion",
)


class MeterlessError(RuntimeError):
    """Safe, user-facing Runtime error; never contains credentials."""


@dataclass
class MeterlessConfig:
    base_url: str = DEFAULT_BASE_URL
    token: str = ""
    routing_mode: str = DEFAULT_ROUTING_MODE

    def __post_init__(self):
        # Rechazar tokens vacíos o placeholders de desarrollo
        token_str = (self.token or "").strip().lower()
        if not token_str or token_str in ("rt-local", "your-token-here", "placeholder"):
            raise MeterlessError("El token de Runtime de Meterless no es válido o está vacío.")

    @classmethod
    def from_env(cls) -> "MeterlessConfig":
        return cls(
            base_url=os.getenv("METERLESS_BASE_URL", DEFAULT_BASE_URL),
            token=os.getenv("METERLESS_RUNTIME_TOKEN", ""),
            routing_mode=os.getenv("METERLESS_ROUTING_MODE", DEFAULT_ROUTING_MODE),
        )


def normalize_base_url(value: str) -> str:
    """Normalize pasted Runtime endpoints to ``scheme://host[:port]/v1``."""
    value = (value or DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL
    if "://" not in value:
        value = "http://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MeterlessError("La URL de Nightshift debe ser una dirección HTTP o HTTPS válida.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise MeterlessError("Pega solo la URL base del Runtime; no incluyas credenciales en la URL.")
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/models", "/healthz"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if path.endswith("/v1"):
        path = path[:-3]
    if path in {"", "/"}:
        path = ""
    return f"{parsed.scheme}://{parsed.netloc}{path}/v1"


class MeterlessClient:
    def __init__(self, config: MeterlessConfig, timeout: float = DEFAULT_TIMEOUT_SECONDS, session: Any = None):
        self.config = config
        self.timeout = timeout
        self.session = session or requests

    @property
    def base_url(self) -> str:
        return normalize_base_url(self.config.base_url)

    @property
    def api_key(self) -> str:
        return self.config.token

    def _headers(self, chat: bool = False) -> Dict[str, str]:
        """Acepta la opción chat=True para ajustar el scope en peticiones de chat."""
        headers = {
            "Content-Type": "application/json",
            "meterless-app": APP_ID,
            "meterless-scope": "user" if chat else "user",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def list_models(self) -> dict[str, Any]:
        """Runtime discovery is the source of truth for mode IDs and auth state."""
        try:
            response = self.session.get(
                f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout
            )
            if response.status_code in (401, 403):
                raise MeterlessError("Nightshift está accesible, pero rechazó el token (no autorizado). Verifica o renueva el token.")
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", []) if isinstance(payload, dict) else []
            models = [item for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)
                      and item["id"].startswith("meterless/")]
            return {"ok": True, "state": "online" if models else "offline", "models": models, "count": len(models)}
        except MeterlessError:
            raise
        except requests.RequestException as exc:
            raise MeterlessError(f"No se pudo consultar el descubrimiento de Nightshift ({type(exc).__name__}).") from None
        except (ValueError, TypeError) as exc:
            raise MeterlessError(f"Nightshift respondió con un formato inesperado ({type(exc).__name__}).") from None

    def check_connection(self) -> dict[str, Any]:
        """Check /v1/models; /healthz alone is not proof the provider is ready."""
        try:
            result = self.list_models()
            if result["count"]:
                return {"ok": True, "stage": "discovery", "state": "online",
                        "message": f"Nightshift está online. Se descubrieron {result['count']} modos.",
                        "count": result["count"]}
            return {"ok": False, "stage": "discovery", "state": "offline",
                    "message": "Nightshift respondió, pero no devolvió modos meterless/ disponibles.", "count": 0}
        except MeterlessError as exc:
            message = str(exc)
            state = "unauthorized" if "no autorizado" in message.lower() or "rechazó el token" in message.lower() else "offline"
            return {"ok": False, "stage": "authentication" if state == "unauthorized" else "connection",
                    "state": state, "message": message}

    def chat(self, messages: list[dict[str, str]], routing_mode: str | None = None) -> dict[str, Any]:
        mode = (routing_mode or self.config.routing_mode or DEFAULT_ROUTING_MODE).strip()
        if not mode.startswith("meterless/") or len(mode) > 160:
            raise MeterlessError("El modo debe ser un ID descubierto con formato meterless/… .")
        body = {"model": mode, "messages": messages, "stream": False}
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(chat=True), json=body, timeout=self.timeout,
            )
            if response.status_code in (401, 403):
                raise MeterlessError("Nightshift está accesible, pero rechazó el token (no autorizado). Verifica o renueva el token.")
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise MeterlessError("Nightshift devolvió una respuesta vacía o con formato inesperado.")
            return {"ok": True, "provider": "meterless", "model": payload.get("model", mode), "answer": content.strip()}
        except MeterlessError:
            raise
        except requests.Timeout:
            raise MeterlessError("La solicitud tardó demasiado. Nightshift puede estar cargando el modelo; inténtalo de nuevo.") from None
        except requests.RequestException as exc:
            raise MeterlessError(f"La solicitud de texto a Nightshift falló ({type(exc).__name__}).") from None
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise MeterlessError(f"Nightshift respondió con un formato inesperado ({type(exc).__name__}).") from None