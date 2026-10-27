import os
import uuid
import requests


def run_sql(sql_query: str) -> list | dict:
  """Ejecuta una consulta SQL en la API REST de Zetaris[cite: 1]."""
  zetaris_url = os.environ.get(
      "ZETARIS_REST_URL", "http://localhost:8888/api/v1.0"
  ).rstrip("/")
  org_id = os.environ.get("ZETARIS_ORG_ID", "1")
  api_key = os.environ.get("ZETARIS_API_KEY", "")

  # Limpiar bloques markdown si el LLM los incluye
  clean_sql = (
      sql_query.replace("```sql", "")
      .replace("```", "")
      .strip()
      .rstrip(";")
  )

  endpoint = f"{zetaris_url}/sql-editor/sqls/run"
  headers = {
      "Authorization": f"Bearer {api_key}",
      "X-Org-ID": str(org_id),  # Requerido por Zetaris[cite: 1]
      "X-Request-ID": str(uuid.uuid4()),  # UUID fresco por petición[cite: 1]
      "Content-Type": "application/json",
  }

  payload = {
      "queryId": str(uuid.uuid4()),
      "sql": clean_sql,
      "source": "SqlEditor",
      "limit": 100,
  }

  try:
    response = requests.post(
        endpoint, headers=headers, json=payload, timeout=30
    )

    if response.status_code != 200:
      return {"error": f"HTTP {response.status_code}: {response.text[:200]}"}

    data = response.json()
    return data.get("data", [])
  except Exception as e:
    return {"error": f"Error de conexión con Zetaris: {str(e)}"}