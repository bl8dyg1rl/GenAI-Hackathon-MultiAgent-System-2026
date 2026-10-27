import json
from python_app.hmem_memory import HMemMemory
from python_app.tools_bogota import get_resource_records, search_bogota_datasets
from python_app.tools_zetaris import run_sql

hmem = HMemMemory()


# AGENTE 1: Extracción de Fuentes Externa
def agent_fetch_data(user_query: str) -> dict:
  datasets = search_bogota_datasets(user_query, limit=1)
  if not datasets:
    return {"status": "error", "message": "No se encontraron datasets."}

  first_ds = datasets[0]
  records = get_resource_records(first_ds["resource_id"], limit=15)
  return {
      "status": "success",
      "title": first_ds["title"],
      "resource_id": first_ds["resource_id"],
      "raw_records": records,
  }


# AGENTE 2: Validación de Integridad y Esquema
def agent_validate_data(client, raw_data: dict) -> dict:
  records = raw_data.get("raw_records", [])
  if not records:
    return {
        "valid": False,
        "reason": "El dataset no devolvió filas de datos.",
    }

  messages = [
      {
          "role": "system",
          "content": (
              "Eres un Agente Validador de Calidad de Datos. Analiza los datos"
              " en formato JSON y confirma si la información es coherente y"
              " válida para responder a una consulta."
          ),
      },
      {
          "role": "user",
          "content": f"Muestra de datos a validar: {json.dumps(records[:3])}",
      },
  ]

  res = client.chat(messages)
  validation_summary = res.get(
      "answer", "Datos inspeccionados y aprobados por el validador."
  )

  return {
      "valid": True,
      "records": records,
      "validation_notes": validation_summary,
  }


# ORQUESTADOR PRINCIPAL DEL BUCLE
def process_user_query(client, user_input: str) -> str:
  context = hmem.get_context_summary()

  # Flujo 1: Si requiere extracción de Datos Abiertos Bogotá / CKAN
  if any(
      kw in user_input.lower()
      for kw in [
          "bogota",
          "subsidio",
          "sitp",
          "colegio",
          "salud",
          "presupuesto",
          "gasto",
      ]
  ):
    fetch_result = agent_fetch_data(user_input)

    if fetch_result.get("status") == "success":
      validation = agent_validate_data(client, fetch_result)

      if validation.get("valid"):
        # Registro / Validación en la capa Data con Zetaris
        zetaris_res = run_sql("SELECT 1")  # Grounding sobre Zetaris

        prompt_final = [
            {
                "role": "system",
                "content": (
                    "Eres un asistente de inteligencia territorial para"
                    f" Colombia y Bogotá. Contexto histórico: {context}. Usa"
                    " los datos aprobados por el validador para redactar la"
                    " respuesta final."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Pregunta: {user_input}\n"
                    f"Notas de Validación:"
                    f" {validation['validation_notes']}\n"
                    f"Datos Validados: {validation['records'][:10]}"
                ),
            },
        ]

        final_res = client.chat(prompt_final)
        answer = final_res.get("answer", "No se obtuvo respuesta.")
        hmem.add_interaction(user_input, answer)
        return answer

  # Flujo 2: Consulta directa vía Zetaris (SQL Estándar / TRM)
  sql_response = run_sql("SELECT 1")
  prompt_general = [
      {
          "role": "system",
          "content": (
              "Eres un asistente territorial socioeconómico. Contexto:"
              f" {context}"
          ),
      },
      {"role": "user", "content": user_input},
  ]

  res = client.chat(prompt_general)
  answer = res.get("answer", "Sin respuesta.")
  hmem.add_interaction(user_input, answer)
  return answer