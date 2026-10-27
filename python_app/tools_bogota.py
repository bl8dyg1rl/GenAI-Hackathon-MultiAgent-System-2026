import requests

CKAN_SEARCH_URL = "https://datosabiertos.bogota.gov.co/api/3/action/package_search"
CKAN_DATASTORE_URL = "https://datosabiertos.bogota.gov.co/api/3/action/datastore_search"


def search_bogota_datasets(query: str, limit: int = 3) -> list:
    """Busca datasets en Datos Abiertos Bogotá mediante la API de CKAN."""
    try:
        response = requests.get(
            CKAN_SEARCH_URL, params={"q": query, "rows": limit}, timeout=15
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            return []

        results = []
        for pkg in data["result"]["results"]:
            for resource in pkg.get("resources", []):
                if resource.get("datastore_active") or resource.get("format") in ["CSV", "JSON"]:
                    results.append({
                        "title": pkg.get("title"),
                        "resource_id": resource["id"],
                        "name": resource.get("name"),
                        "description": pkg.get("notes", "")[:150],
                    })
        return results[:limit]
    except Exception as e:
        print(f"[Error buscando en CKAN]: {e}")
        return []


def get_resource_records(resource_id: str, limit: int = 50) -> list:
    """Obtiene los registros de un recurso específico usando su resource_id (UUID)."""
    try:
        response = requests.get(
            CKAN_DATASTORE_URL,
            params={"resource_id": resource_id, "limit": limit},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("success"):
            return data["result"].get("records", [])
        return []
    except Exception as e:
        print(f"[Error consultando recurso {resource_id}]: {e}")
        return []


def get_bogota_data_dynamic(user_topic: str, limit: int = 20) -> dict:
    """Busca un tema, extrae el UUID automáticamente y devuelve los registros."""
    datasets = search_bogota_datasets(user_topic, limit=1)
    if not datasets:
        return {"error": f"No se encontraron datasets para '{user_topic}'"}
    
    first_ds = datasets[0]
    resource_id = first_ds["resource_id"]
    records = get_resource_records(resource_id, limit=limit)
    
    return {
        "dataset_title": first_ds["title"],
        "resource_id": resource_id,
        "records": records
    }