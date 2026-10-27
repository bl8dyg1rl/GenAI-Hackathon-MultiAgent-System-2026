from typing import Dict, Any


def route_intent(user_query: str) -> Dict[str, Any]:
  """Clasifica la consulta del usuario para determinar el flujo o herramienta adecuada (Scout Intent)."""
  query_lower = user_query.lower()

  # Intención: Consulta de Base de Datos Socioeconómica (DANE / Zetaris)
  if any(
      kw in query_lower
      for kw in [
          "poblacion",
          "dane",
          "departamento",
          "municipio",
          "sql",
          "base de datos",
          "pobreza",
          "ingreso",
      ]
  ):
    return {
        "intent": "DATA_QUERY",
        "description": "Consulta de datos socioeconómicos en Zetaris",
        "action": "execute_sql",
    }

  # Intención: Análisis general / Conversación de Inteligencia Territorial
  return {
      "intent": "GENERAL_ANALYSIS",
      "description": "Consulta de análisis socioeconómico general",
      "action": "chat_llm",
  }