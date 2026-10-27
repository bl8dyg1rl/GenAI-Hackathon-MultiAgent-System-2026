import unittest
from unittest.mock import Mock

from python_app.zetaris import ZetarisClient, ZetarisConfig, ZetarisError, validate_read_only_sql


class ZetarisTests(unittest.TestCase):
    def setUp(self):
        self.tables = ["COLOMBIA_STATS.desempleo"]

    def test_accepts_bounded_select_for_allowlisted_table(self):
        sql = validate_read_only_sql("SELECT anio, tasa FROM COLOMBIA_STATS.desempleo", self.tables)
        self.assertEqual(sql, "SELECT anio, tasa FROM COLOMBIA_STATS.desempleo LIMIT 100")

    def test_rejects_write_multi_statement_and_unapproved_table(self):
        for sql in (
            "DELETE FROM COLOMBIA_STATS.desempleo",
            "SELECT * FROM OTHER.table LIMIT 2",
            "SELECT * FROM COLOMBIA_STATS.desempleo; DROP TABLE x",
            "SELECT * FROM COLOMBIA_STATS.desempleo -- comment",
            "SELECT * FROM COLOMBIA_STATS.desempleo, SECRET.private_data LIMIT 2",
        ):
            with self.subTest(sql=sql), self.assertRaises(ZetarisError):
                validate_read_only_sql(sql, self.tables)

    def test_rejects_limit_over_100(self):
        with self.assertRaises(ZetarisError):
            validate_read_only_sql("SELECT * FROM COLOMBIA_STATS.desempleo LIMIT 1000", self.tables)

    def test_query_uses_documented_payload_and_parses_rows(self):
        session = Mock()
        response = Mock(status_code=200)
        response.json.return_value = {"headers": ["anio", "tasa"], "data": [[2023, 10.5], [2024, 9.7]], "queryToken": "opaque"}
        session.post.return_value = response
        config = ZetarisConfig(base_url="http://127.0.0.1:8888/api/v1.0", token="id-token",
                               allowed_tables=self.tables)
        client = ZetarisClient(config, session=session)
        result = client.query("SELECT anio, tasa FROM COLOMBIA_STATS.desempleo LIMIT 10")
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["rows"][0], {"anio": 2023, "tasa": 10.5})
        args = session.post.call_args
        self.assertTrue(args.args[0].endswith("/sql-editor/sqls/run-query"))
        self.assertEqual(args.kwargs["headers"]["Authorization"], "Bearer id-token")
        self.assertEqual(args.kwargs["json"], {"select": "SELECT anio, tasa FROM COLOMBIA_STATS.desempleo LIMIT 10", "pageLimit": 100})

    def test_unauthorized_token_is_reported(self):
        session = Mock()
        session.post.return_value = Mock(status_code=401)
        client = ZetarisClient(ZetarisConfig(token="bad", allowed_tables=self.tables), session=session)
        with self.assertRaisesRegex(ZetarisError, "rechazó el token"):
            client.query("SELECT * FROM COLOMBIA_STATS.desempleo LIMIT 1")


if __name__ == "__main__":
    unittest.main()
