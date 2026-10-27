from pathlib import Path
from dotenv import load_dotenv

# 1. Cargar variables de entorno con ruta explícita
CURRENT_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=CURRENT_DIR / ".env")

from python_app.agent_loop import process_user_query
from python_app.meterless import MeterlessClient, MeterlessConfig, MeterlessError
from python_app.scout_intent import route_intent


def main():
  print("=== COLOMBIA DATA INTELLIGENCE MULTI-AGENT ===")

  config = MeterlessConfig.from_env()
  client = MeterlessClient(config)

  conn_status = client.check_connection()
  print(f"Estado del Runtime Meterless: {conn_status.get('message')}\n")
  print("Sistema listo. Ingrese una consulta (o 'salir' para terminar):")

  while True:
    try:
      user_input = input("\n> ")
      if user_input.lower().strip() in ("salir", "exit", "quit"):
        print("Saliendo del sistema...")
        break
      if not user_input.strip():
        continue

      # 2. Scout Intent: Clasificación previa de la intención
      intent_info = route_intent(user_input)
      print(f"[Scout Intent] Intención: {intent_info['intent']}")

      # 3. Procesar la consulta mediante el agente con capacidad de Tool Calling en Zetaris
      response_text = process_user_query(client, user_input)

      print("\n--- RESPUESTA FINAL ---")
      print(response_text)
      print("-----------------------")

    except MeterlessError as err:
      print(f"\n[Error de Meterless]: {err}")
    except Exception as err:
      print(f"\n[Error Inesperado]: {err}")


if __name__ == "__main__":
  main()