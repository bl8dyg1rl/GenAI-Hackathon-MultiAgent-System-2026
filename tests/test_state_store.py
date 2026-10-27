import json
import os
import tempfile
import unittest

from python_app.state_store import StateStore


class StateStoreTests(unittest.TestCase):
    def test_logs_events_messages_and_redacts_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(os.path.join(tmp, "events.sqlite3"))
            store.create_run("run-1", "trace-1", "Busca estadísticas", "research.dataset_discovery", 0.9)
            store.log_event("run-1", "DataScout", "model.request", "Calling model",
                            {"prompt": "hello", "authorization": "Bearer real-secret-token"}, success=True)
            store.send_message("run-1", "DataScout", "Analyst", "dataset", {"candidate_count": 2})
            inbox = store.receive_messages("run-1", "Analyst")
            self.assertEqual(len(inbox), 1)
            events = store.list_events("run-1")
            self.assertTrue(any(e["event_type"] == "agent.message.received" for e in events))
            logged_request = next(e for e in events if e["event_type"] == "model.request")
            self.assertEqual(logged_request["payload"]["authorization"], "[REDACTED]")
            messages = store.list_messages("run-1")
            self.assertTrue(messages[0]["delivered"])


if __name__ == "__main__":
    unittest.main()
