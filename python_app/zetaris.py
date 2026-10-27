"""Read-only Zetaris REST query adapter.

The REST payload follows Zetaris' documented SQL query contract:
POST <base>/sql-editor/sqls/run with {"sql": "SELECT ...", "limit": N}.
Actual access depends on the configured Zetaris instance and its bearer/id token.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict
from urllib.parse import urlparse

import requests

DEFAULT_ZETARIS_BASE = "http://127.0.0.1:8888/api/v1.0"
DEFAULT_QUERY_PATH = "sql-editor/sqls/run-query"
MAX_ROWS = 100
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_$]*(?:\.[A-Za-z_][A-Za-z0-9_$]*)*"
_TABLE_PATTERN = re.compile(_IDENTIFIER)
_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|CALL|EXEC|EXECUTE|INTO|COPY|LOAD|UNLOAD)\b",
    re.IGNORECASE,
)


class ZetarisError(RuntimeError):
    """Safe Zetaris connection, authentication, or query error."""


@dataclass
class ZetarisConfig:
    base_url: str = DEFAULT_ZETARIS_BASE
    token: str = ""
    query_path: str = DEFAULT_QUERY_PATH
    allowed_tables: list[str] = field(default_factory=list)
    table_map: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "ZetarisConfig":
        tables = [t.strip() for t in os.getenv("ZETARIS_TABLES", "").split(",") if t.strip()]
        try:
            table_map = json.loads(os.getenv("ZETARIS_TABLE_MAP", "{}"))
            if not isinstance(table_map, dict):
                table_map = {}
        except json.JSONDecodeError:
            table_map = {}
        return cls(
            base_url=os.getenv("ZETARIS_API_BASE_URL", DEFAULT_ZETARIS_BASE).rstrip("/"),
            token=os.getenv("ZETARIS_API_TOKEN", ""),
            query_path=os.getenv("ZETARIS_QUERY_PATH", DEFAULT_QUERY_PATH).strip("/"),
            allowed_tables=tables,
            table_map={str(k): str(v) for k, v in table_map.items()},
            timeout=float(os.getenv("ZETARIS_QUERY_TIMEOUT", "30")),
        )


def normalize_zetaris_base_url(value: str) -> str:
    value = (value or DEFAULT_ZETARIS_BASE).strip().rstrip("/") or DEFAULT_ZETARIS_BASE
    if "://" not in value:
        value = "http://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ZetarisError("La URL de Zetaris debe ser HTTP o HTTPS.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ZetarisError("La URL de Zetaris no debe incluir credenciales, consulta ni fragmento.")
    return value


def validate_table_name(table: str) -> str:
    table = (table or "").strip()
    if not table or not _TABLE_PATTERN.fullmatch(table):
        raise ZetarisError(f"Nombre de tabla no válido: {table!r}.")
    return table


def validate_read_only_sql(sql: str, allowed_tables: list[str] | None = None, *, max_rows: int = MAX_ROWS) -> str:
    """Accept one bounded SELECT referencing only configured allow-list tables."""
    value = (sql or "").strip()
    value = re.sub(r"^```(?:sql)?\s*|\s*```$", "", value, flags=re.IGNORECASE).strip()
    if value.endswith(";"):
        value = value[:-1].rstrip()
    if not value:
        raise ZetarisError("La consulta SQL está vacía.")
    if ";" in value or "--" in value or "/*" in value or "*/" in value:
        raise ZetarisError("La consulta contiene múltiples sentencias o comentarios SQL no permitidos.")
    if not re.match(r"^SELECT\b", value, re.IGNORECASE):
        raise ZetarisError("Solo se permiten consultas SELECT de solo lectura.")
    if _FORBIDDEN_SQL.search(value):
        raise ZetarisError("La consulta contiene una operación SQL no permitida.")
    if re.search(r"\b(FOR\s+UPDATE|INFORMATION_SCHEMA|SYS\.)\b", value, re.IGNORECASE):
        raise ZetarisError("La consulta intenta acceder a una zona o bloqueo SQL no permitido.")
    if re.search(r"\b(FROM|JOIN)\s*\(", value, re.IGNORECASE):
        raise ZetarisError("No se permiten subconsultas generadas dinámicamente en el MVP.")
    if re.search(rf"\bFROM\s+{_IDENTIFIER}(?:\s+(?:AS\s+)?[A-Za-z_][A-Za-z0-9_$]*)?\s*,", value, re.IGNORECASE):
        raise ZetarisError("No se permiten joins mediante coma; usa JOIN explícitos sobre tablas autorizadas.")

    if allowed_tables:
        allowed = {validate_table_name(t).casefold(): validate_table_name(t) for t in allowed_tables}
        references = re.findall(rf"\b(?:FROM|JOIN)\s+({_IDENTIFIER})", value, re.IGNORECASE)
        if not references:
            raise ZetarisError("La consulta debe leer al menos una tabla permitida de Zetaris.")
        for table in references:
            if table.casefold() not in allowed:
                raise ZetarisError(f"La tabla {table} no está en la lista permitida de Zetaris.")

    limits = re.findall(r"\bLIMIT\s+(\d+)\b", value, re.IGNORECASE)
    if len(limits) > 1:
        raise ZetarisError("Solo se permite un LIMIT en la consulta.")
    if limits:
        limit = int(limits[0])
        if limit < 1 or limit > max_rows:
            raise ZetarisError(f"El límite debe estar entre 1 y {max_rows} filas.")
    else:
        value += f" LIMIT {max_rows}"
    return value


class ZetarisClient:
    def __init__(self, config: ZetarisConfig, *, session: Any = None):
        self.config = config
        self.session = session or requests

    @property
    def api_key(self) -> str:
        """Devuelve el token/clave API configurado."""
        return self.config.token

    def _headers(self) -> dict[str, str]:
        token = (self.config.token or "").strip()
        if not token:
            raise ZetarisError("Falta el token de acceso de la API de Zetaris. Configúralo en Ajustes o en ZETARIS_API_TOKEN.")
        return {
            "Authorization": f"Bearer {token}",
            "X-Org-ID": str(os.getenv("ZETARIS_ORG_ID", "1")),
            "X-Request-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def query(self, sql: str, limit: int = 100) -> Dict[str, Any]:
        allowed = getattr(self.config, "allowed_tables", [])
        
        # 1. Validar la consulta SQL de solo lectura
        validated_sql = validate_read_only_sql(sql, allowed)
        
        # 2. Construir la URL según el query_path configurado
        query_path = getattr(self.config, "query_path", "sql-editor/sqls/run-query").strip("/")
        url = f"{self.config.base_url.rstrip('/')}/{query_path}"
        
        # 3. Construir el payload según el endpoint destino
        if query_path.endswith("run-query"):
            payload = {
                "select": validated_sql,
                "pageLimit": limit
            }
        else:
            payload = {
                "queryId": str(uuid.uuid4()),
                "sql": validated_sql,
                "source": "SqlEditor",
                "limit": limit
            }
        
        response = self.session.post(
            url, 
            headers=self._headers(), 
            json=payload, 
            timeout=getattr(self.config, "timeout", 60.0)
        )
        
        # 4. Manejar respuestas no autorizadas (401 / 403)
        if response.status_code in (401, 403):
            raise ZetarisError("Zetaris rechazó el token (no autorizado). Verifica o renueva la API key.")
            
        response.raise_for_status()
        payload_data = response.json() if isinstance(response.json(), dict) else {}
        
        # 5. Parsear encabezados y filas
        headers_list, rows = self._parse_result(payload_data)
        
        return {
            "ok": True,
            "headers": headers_list,
            "rows": rows,
            "row_count": len(rows),
            "query_token": payload_data.get("queryToken")
        }

    @staticmethod
    def _parse_result(payload: Any) -> tuple[list[str], list[dict[str, Any]]]:
        if not isinstance(payload, dict):
            raise ZetarisError("La respuesta de Zetaris no es un objeto JSON.")
        candidate = payload
        for key in ("result", "response"):
            if isinstance(candidate.get(key), dict) and not ("headers" in candidate or "data" in candidate):
                candidate = candidate[key]
        headers_raw = candidate.get("headers") or candidate.get("columns") or []
        data_raw = candidate.get("data") or candidate.get("rows") or []
        headers: list[str] = []
        for item in headers_raw if isinstance(headers_raw, list) else []:
            if isinstance(item, str):
                headers.append(item)
            elif isinstance(item, dict):
                headers.append(str(item.get("name") or item.get("columnName") or item.get("field") or "column"))
        rows: list[dict[str, Any]] = []
        if isinstance(data_raw, list):
            for row in data_raw:
                if isinstance(row, dict):
                    rows.append(row)
                elif isinstance(row, (list, tuple)):
                    if not headers:
                        headers = [f"column_{i + 1}" for i in range(len(row))]
                    rows.append({headers[i] if i < len(headers) else f"column_{i + 1}": value
                                 for i, value in enumerate(row)})
        if not headers and rows:
            headers = list(rows[0].keys())
        if any(k in candidate for k in ("error", "errors")) and candidate.get("error"):
            raise ZetarisError("Zetaris reportó un error al ejecutar la consulta.")
        return headers, rows

    def preview_table(self, table: str, *, limit: int = 3) -> dict[str, Any]:
        safe_table = validate_table_name(table)
        if self.config.allowed_tables and safe_table.casefold() not in {t.casefold() for t in self.config.allowed_tables}:
            raise ZetarisError(f"La tabla {safe_table} no está autorizada.")
        query = f"SELECT * FROM {safe_table} LIMIT {max(1, min(limit, 10))}"
        return self.query(query, limit=max(1, min(limit, 10)))

    def check_connection(self) -> dict[str, Any]:
        if not self.config.allowed_tables:
            return {"ok": False, "state": "not_configured", "message": "Configura al menos una tabla de lectura permitida en Zetaris."}
        table = self.config.allowed_tables[0]
        try:
            result = self.preview_table(table, limit=1)
            return {"ok": True, "state": "online", "message": f"Zetaris respondió. Tabla comprobada: {table}.",
                    "row_count": result["row_count"]}
        except ZetarisError as exc:
            return {"ok": False, "state": "error", "message": str(exc)}