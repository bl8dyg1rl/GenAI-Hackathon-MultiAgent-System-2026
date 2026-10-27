"""Official open-data catalog discovery and Zetaris sources mapping.

This module provides:
1. Search across dataset metadata in datos.gov.co.
2. Static configuration mapping of registered Zetaris tables for Multi-Agent routing.
"""
from __future__ import annotations

from typing import Any

import requests

CATALOG_URL = "https://www.datos.gov.co/api/catalog/v1"

# =====================================================================
# DICCIONARIO DE FUENTES REGISTRADAS EN ZETARIS (REQUERIDO POR MULTIAGENTE)
# =====================================================================
SOURCES_CONFIG = {
    "banrep": {
        "table": "DATOS_GOV.banrep_trm",
        "description": "Tasa de Cambio Representativa del Mercado (TRM) e indicadores del Banco de la República",
        "columns": ["valor", "unidad", "vigenciadesde", "vigenciahasta"]
    },
    "dian": {
        "table": "DATOS_GOV.dian_recaudo",
        "description": "Recaudo tributario por departamento y seccional de la DIAN",
        "columns": ["departamento", "anio", "concepto", "recaudo"]
    },
    "datos_gov": {
        "table": "DATOS_GOV.datos_gov_indicadores",
        "description": "Indicadores económicos y sociales regionales de Datos Abiertos Colombia",
        "columns": ["departamento", "indicador", "valor", "fecha"]
    }
}


# =====================================================================
# BÚSQUEDA DE CATÁLOGO / METADATOS
# =====================================================================
def search_datos_abiertos(query: str, limit: int = 5, timeout: int = 10) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {"source": "datos_abiertos", "query": query, "results": [], "error": "La búsqueda no puede estar vacía."}
    try:
        response = requests.get(
            CATALOG_URL,
            params={"search_context": "www.datos.gov.co", "q": query, "limit": max(1, min(int(limit), 20))},
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "colombia-data-intelligence/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        results: list[dict[str, Any]] = []
        for item in payload.get("results", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            resource = item.get("resource") or {}
            metadata = item.get("metadata") or {}
            dataset_id = resource.get("id")
            results.append({
                "id": dataset_id,
                "name": (metadata.get("name") or resource.get("name") or "Dataset sin título")[:300],
                "description": str(metadata.get("description") or "")[:1200],
                "updated_at": metadata.get("data_updated_at"),
                "link": item.get("link") or resource.get("permalink"),
                "source": "Datos Abiertos Colombia",
            })
        return {"source": "datos_abiertos", "query": query, "results": results[:limit], "error": None}
    except requests.Timeout:
        return {"source": "datos_abiertos", "query": query, "results": [], "error": "La búsqueda del catálogo excedió el tiempo máximo."}
    except requests.RequestException as exc:
        return {"source": "datos_abiertos", "query": query, "results": [], "error": f"No se pudo consultar el catálogo ({type(exc).__name__})."}
    except (ValueError, TypeError) as exc:
        return {"source": "datos_abiertos", "query": query, "results": [], "error": f"El catálogo devolvió un formato inesperado ({type(exc).__name__})."}