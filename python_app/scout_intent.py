from typing import Any, Dict


def route_intent(user_query: str) -> Dict[str, Any]:
  query_lower = user_query.lower()

  # Lista ampliada de palabras clave para capturar datos socioeconómicos, territoriales y financieros
  keywords_data = [
      # Geografía y Territorios
      "bogota",
      "departamento",
      "municipio",
      "colombia",
      "localidad",
      "region",
      # Entidades y Fuentes
      "dane",
      "zetaris",
      "ckan",
      "camara",
      "alcaldia",
      # Indicadores Socioeconómicos
      "poblacion",
      "pobreza",
      "ingreso",
      "pib",
      "desempleo",
      "trm",
      "dolar",
      "subsidio",
      # Finanzas y Gestión
      "presupuesto",
      "gasto",
      "inversion",
      "ejecucion",
      "dinero",
      "finanzas",
      # Sectores (Movilidad, Educación, Salud)
      "sitp",
      "colegio",
      "educacion",
      "salud",
      "transporte",
      # Consultas de Datos / SQL
      "sql",
      "base de datos",
      "tabla",
      "datos",
      "registro",
      "consultar",
  ]

  if any(kw in query_lower for kw in keywords_data):
    return {
        "intent": "DATA_QUERY",
        "description": "Consulta de datos socioeconómicos/territoriales",
        "action": "execute_tools",
    }

  return {
      "intent": "GENERAL_ANALYSIS",
      "description": "Consulta general",
      "action": "chat_llm",
  }