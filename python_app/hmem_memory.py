import json
from pathlib import Path


class HMemMemory:
  """Implementación simplificada del motor H-Mem para gestionar memoria persistente de sesión."""

  def __init__(self, storage_file: str = "hmem_context.json"):
    self.storage_path = Path(__file__).resolve().parent / storage_file
    self.memory = self._load_memory()

  def _load_memory(self) -> dict:
    if self.storage_path.exists():
      try:
        with open(self.storage_path, "r", encoding="utf-8") as f:
          return json.load(f)
      except Exception:
        return {"session_history": [], "user_preferences": {}}
    return {"session_history": [], "user_preferences": {}}

  def save_memory(self):
    with open(self.storage_path, "w", encoding="utf-8") as f:
      json.dump(self.memory, f, ensure_ascii=False, indent=2)

  def add_interaction(self, user_query: str, agent_response: str):
    self.memory["session_history"].append({
        "user": user_query,
        "assistant": agent_response,
    })
    # Conservar únicamente las últimas 5 interacciones para un contexto liviano
    self.memory["session_history"] = self.memory["session_history"][-5:]
    self.save_memory()

  def get_context_summary(self) -> str:
    if not self.memory["session_history"]:
      return "No hay contexto previo almacenado."
    context_str = "Contexto previo del usuario (H-Mem):\n"
    for item in self.memory["session_history"]:
      context_str += (
          f"- Usuario: {item['user']}\n  Respuesta: {item['assistant']}\n"
      )
    return context_str