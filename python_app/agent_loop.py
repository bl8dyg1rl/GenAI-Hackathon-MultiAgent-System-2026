import json
from python_app.tools_zetaris import run_sql

SYSTEM_PROMPT = """
Eres un agente experto en datos socioeconómicos de Colombia.
Tienes acceso a la herramienta `run_sql` conectada a Zetaris para consultar la base de datos.
Si el usuario pregunta por datos específicos (población, departamentos, municipios, DANE):
1. Escribe la consulta SQL adecuada para Zetaris.
2. Usa el resultado de la consulta para responder con precisión y contexto geográfico/socioeconómico.
"""


def process_user_query(client, user_input: str):
  messages = [
      {"role": "system", "content": SYSTEM_PROMPT},
      {"role": "user", "content": user_input},
  ]

  # 1. Enviar primera solicitud a Nemotron a través de Meterless
  response = client.chat(messages)
  answer = response.get("answer", "")

  # Si el modelo devuelve una consulta SQL dentro de un bloque de código
  if "SELECT" in answer.upper():
    # Extraer la consulta SQL simple del texto del modelo
    sql_start = answer.upper().find("SELECT")
    sql_end = answer.find(";", sql_start)
    sql_query = (
        answer[sql_start : sql_end + 1]
        if sql_end != -1
        else answer[sql_start:]
    )

    print(f"\n[Ejecutando SQL en Zetaris]: {sql_query}")

    # 2. Ejecutar la consulta en Zetaris
    db_result = run_sql(sql_query)
    print(f"[Resultado de Datos]: {db_result}")

    # 3. Dar contextualización final con los datos devueltos
    follow_up_messages = messages + [
        {"role": "assistant", "content": answer},
        {
            "role": "user",
            "content": (
                "Aquí están los datos devueltos por la base de datos:"
                f" {json.dumps(db_result)}. Genera un resumen claro en español."
            ),
        },
    ]
    final_response = client.chat(follow_up_messages)
    return final_response.get("answer", "No se pudo interpretar el resultado.")

  return answer