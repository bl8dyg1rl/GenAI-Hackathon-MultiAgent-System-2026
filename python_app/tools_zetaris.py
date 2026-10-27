import os
import uuid
import requests


def run_sql(sql_query: str) -> list | dict:
  """Ejecuta una consulta SQL sobre la API REST de Zetaris y retorna los resultados."""
  zetaris_url = os.environ.get(
      "ZETARIS_REST_URL", "http://localhost:8888/api/v1.0"
  ).rstrip("/")
  org_id = os.environ.get("ZETARIS_ORG_ID", "1")
  api_key = os.environ.get("ZETARIS_API_KEY", "")

  if not api_key:
    raise ValueError("ZETARIS_API_KEY no está configurada en el archivo .env")

  endpoint = f"{zetaris_url}/sql-editor/sqls/run"
  headers = {
      "Authorization": f"Bearer {api_key}",
      "X-Org-ID": org_id,
      "X-Request-ID": str(uuid.uuid4()),
      "Content-Type": "application/json",
  }

  payload = {
      "queryId": str(uuid.uuid4()),
      "sql": sql_query,
      "source": "SqlEditor",
      "limit": 100,
  }

  try:
    response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data.get("data", [])
  except Exception as e:
    return {"error": f"Error ejecutando SQL en Zetaris: {str(e)}"}