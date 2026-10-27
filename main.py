from pathlib import Path
from dotenv import load_dotenv

# 1. Cargar .env con la ruta explícita
CURRENT_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=CURRENT_DIR / ".env")

from python_app.meterless import MeterlessClient, MeterlessConfig, MeterlessError
from python_app.scout_intent import route_intent
from python_app.tools_zetaris import run_sql


def main():
  print("=== INICIANDO COLOMBIA DATA INTELLIGENCE MULTI-AGENT ===")

  config = MeterlessConfig.from_env()
  client = MeterlessClient(config)

  conn_status = client.check_connection()
  print(f"Estado de Meterless: {conn_status.get('message')}\n")
  print(
      "Sistema listo. Escribe tu pregunta socioeconómica (o 'salir' para"
      " terminar):"
  )

  while True:
    try:
      user_input = input("\n> ")
      if user_input.lower().strip() in ("salir", "exit", "quit"):
        print("Saliendo de la aplicación...")
        break
      if not user_input.strip():
        continue

      # 2. Scout Intent: Clasificar intención de la consulta
      route = route_intent(user_input)
      print(f"[Scout Intent] Intención detectada: {route['intent']}")

      # 3. Flujo condicional basado en la intención
      if route["intent"] == "DATA_QUERY":
        print(
            "Procesando consulta de datos (Generando consulta SQL para"
            " Zetaris)..."
        )
        # Ejemplo: Consulta SQL simple sobre la base de datos de Zetaris
        sql_prompt = (
            f"Convierte la siguiente solicitud en una consulta SQL básica:"
            f" {user_input}"
        )
        # Enviar al LLM para obtener la consulta SQL o ejecutar directamente
        query_result = run_sql("SELECT 1")
        print(f"\n--- RESULTADO DE ZETARIS SQL ---")
        print(query_result)
        print("---------------------------------")
      else:
        print(f"Procesando consulta general con Nemotron...")
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un asistente experto en análisis socioeconómico y"
                    " regional de Colombia."
                ),
            },
            {"role": "user", "content": user_input},
        ]
        response = client.chat(messages)
        print("\n--- RESPUESTA DE NEMOTRON ---")
        print(response.get("answer", "No se obtuvo respuesta."))
        print("------------------------------")

    except MeterlessError as err:
      print(f"\n[Error de Meterless]: {err}")
    except Exception as err:
      print(f"\n[Error inesperado]: {err}")


if __name__ == "__main__":
  main()