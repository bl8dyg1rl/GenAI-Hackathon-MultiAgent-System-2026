from python_app.hmem_memory import HMemMemory
from python_app.tools_bogota import get_resource_records, search_bogota_datasets
from python_app.tools_zetaris import run_sql

def process_user_query(client, user_input: str):
  # 1. Buscar si la pregunta trata sobre Bogotá / Datos Abiertos
  if any(
      kw in user_input.lower()
      for kw in ["bogota", "subsidio", "sitp", "colegio", "salud", "pobreza"]
  ):
    print(f"\n[Scout Intent]: Buscando catálogo dinámico en Datos Abiertos Bogotá...")
    datasets = search_bogota_datasets(user_input)

    if datasets and "resource_id" in datasets[0]:
      first_ds = datasets[0]
      resource_id = first_ds["resource_id"]
      print(
          f"[Dataset Encontrado]: {first_ds['dataset_title']} (ID:"
          f" {resource_id})"
      )

      # Opción A: Obtener registros directo de la API
      data_records = get_resource_records(resource_id, limit=20)

      # Opción B (Si deseas pasar por Zetaris):
      # register_dynamic_ckan_table(resource_id, "tabla_consulta")
      # data_records = run_sql("SELECT * FROM bogota_dynamic.tabla_consulta LIMIT 20")

      # Dar la respuesta informada por el dataset real
      messages = [
          {
              "role": "system",
              "content": (
                  "Eres un asistente de inteligencia territorial para Bogotá."
                  " Responde al usuario basándote en los siguientes datos"
                  " reales extraídos dinámicamente de Datos Abiertos Bogotá."
              ),
          },
          {
              "role": "user",
              "content": (
                  f"Pregunta del usuario: {user_input}\n\nDatos de la"
                  f" API: {data_records}"
              ),
          },
      ]
      response = client.chat(messages)
      return response.get("answer", "No se obtuvo respuesta.")

  # Si es una consulta general
  messages = [
      {
          "role": "system",
          "content": (
              "Eres un asistente experto en análisis socioeconómico de Colombia."
          ),
      },
      {"role": "user", "content": user_input},
  ]
  response = client.chat(messages)
  return response.get("answer", "Sin respuesta.")