import unittest

from miniviking.config import config_from_defaults
from miniviking.openviking import openviking_config
from miniviking.tiers import MEDIUM


class OpenVikingConfigTests(unittest.TestCase):
    def test_openviking_config_uses_openai_provider_shape(self) -> None:
        config = config_from_defaults(MEDIUM, port=9999)
        payload = openviking_config(config)

        self.assertEqual(payload["embedding"]["dense"]["provider"], "openai")
        self.assertEqual(payload["embedding"]["dense"]["api_base"], "http://127.0.0.1:9999/v1")
        self.assertEqual(payload["embedding"]["dense"]["dimension"], 768)
        self.assertEqual(payload["vlm"]["provider"], "openai")
        self.assertEqual(payload["vlm"]["api_base"], "http://127.0.0.1:9999/v1")


if __name__ == "__main__":
    unittest.main()
