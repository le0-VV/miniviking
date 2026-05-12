import threading
import unittest
from dataclasses import replace
from typing import Any

from miniviking.config import config_from_defaults
from miniviking.runtime import ChatResult
from miniviking.server import MinivikingServer
from miniviking.smoke import run_smoke
from miniviking.tiers import SMALL


class FakeRuntime:
    def load(self) -> None:
        return

    def chat(self, messages: list[dict[str, str]], payload: dict[str, Any]) -> ChatResult:
        return ChatResult(content='{"miniviking_smoke": true}', prompt_tokens=7, completion_tokens=5)

    def embed(self, inputs: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in inputs]


class SmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        config = config_from_defaults(SMALL)
        self.config = replace(config, models=replace(config.models, embedding_dimensions=3))
        self.server = MinivikingServer(("127.0.0.1", 0), self.config, FakeRuntime())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def test_run_smoke_accepts_openai_compatible_surface(self) -> None:
        checks = run_smoke(self.config, base_url=f"http://127.0.0.1:{self.server.server_port}/v1")

        self.assertTrue(all(check.ok for check in checks), checks)
        self.assertEqual([check.name for check in checks], ["health", "models", "chat", "embeddings"])


if __name__ == "__main__":
    unittest.main()
