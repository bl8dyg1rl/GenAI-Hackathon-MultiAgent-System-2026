import os
import uuid
import requests


def run_sql(sql_query: str) -> list | dict:
  zetaris_url = os.environ.get(
      "ZETARIS_REST_URL", "http://localhost:8888/api/v1.0"
  ).rstrip("/")
  org_id = os.environ.get("ZETARIS_ORG_ID", "1")  # '1' en entorno local[cite: 2]
  api_key = os.environ.get("ZETARIS_API_KEY", "")

  clean_sql = (
      sql_query.replace("```sql", "")
      .replace("```", "")
      .strip()
      .rstrip(";")
  )

  headers = {
      "Authorization": f"Bearer {api_key}",
      "X-Org-ID": str(org_id),  # Requerido por la API de Zetaris[cite: 2]
      "X-Request-ID": str(uuid.uuid4()),  # UUID fresco por petición[cite: 2]
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
        f"{zetaris_url}/sql-editor/sqls/run",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if response.status_code != 200:
      return {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
    return response.json().get("data", [])
  except Exception as e:
    return {"error": f"Error de conexión con Zetaris: {str(e)}"}