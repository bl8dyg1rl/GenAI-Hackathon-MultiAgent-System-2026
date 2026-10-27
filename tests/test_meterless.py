import unittest
from unittest.mock import Mock

from python_app.meterless import MeterlessClient, MeterlessConfig, MeterlessError, normalize_base_url


class MeterlessTests(unittest.TestCase):
    def test_normalizes_common_urls(self):
        self.assertEqual(normalize_base_url("127.0.0.1:8088"), "http://127.0.0.1:8088/v1")
        self.assertEqual(normalize_base_url("http://127.0.0.1:8088/v1"), "http://127.0.0.1:8088/v1")
        self.assertEqual(normalize_base_url("http://127.0.0.1:8088/v1/chat/completions"), "http://127.0.0.1:8088/v1")
        self.assertEqual(normalize_base_url("http://127.0.0.1:8088/v1/models"), "http://127.0.0.1:8088/v1")

    def test_rejects_placeholder_token(self):
        for token in ("", "rt-local"):
            with self.assertRaises(MeterlessError):
                MeterlessClient(MeterlessConfig(token=token), session=Mock()).list_models()

    def test_discovery_uses_bearer_and_preserves_unknown_meterless_ids(self):
        session = Mock()
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"id": "meterless/auto"}, {"id": "meterless/custom.future-mode"}, {"id": "other-model"}]}
        session.get.return_value = response
        client = MeterlessClient(MeterlessConfig(token="real-token"), session=session)
        result = client.list_models()
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["models"][1]["id"], "meterless/custom.future-mode")
        args = session.get.call_args
        self.assertEqual(args.kwargs["headers"]["Authorization"], "Bearer real-token")
        self.assertEqual(args.kwargs["headers"]["meterless-app"], "colombia-data-intelligence")
        self.assertTrue(args.args[0].endswith("/v1/models"))

    def test_chat_headers_and_route(self):
        session = Mock()
        response = Mock(status_code=200)
        response.json.return_value = {"model": "meterless/auto", "choices": [{"message": {"content": "Respuesta"}}]}
        session.post.return_value = response
        client = MeterlessClient(MeterlessConfig(token="real-token"), session=session)
        result = client.chat([{"role": "user", "content": "Hola"}])
        self.assertEqual(result["answer"], "Respuesta")
        args = session.post.call_args.kwargs
        self.assertEqual(args["headers"]["Authorization"], "Bearer real-token")
        self.assertEqual(args["headers"]["meterless-app"], "colombia-data-intelligence")
        self.assertEqual(args["headers"]["meterless-scope"], "user")
        self.assertEqual(args["json"]["model"], "meterless/auto")

    def test_wrong_token_is_unauthorized_not_offline(self):
        session = Mock()
        response = Mock(status_code=401)
        session.get.return_value = response
        client = MeterlessClient(MeterlessConfig(token="wrong-token"), session=session)
        result = client.check_connection()
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "unauthorized")


if __name__ == "__main__":
    unittest.main()
