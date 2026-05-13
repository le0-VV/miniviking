import json
import socketserver
import threading
import unittest
from typing import Any
from urllib.request import Request, urlopen

from miniviking.config import config_from_defaults
from miniviking.runtime import ChatResult
from miniviking.server import MinivikingServer
from miniviking.tiers import SMALL


class FakeRuntime:
    def load(self) -> None:
        return

    def chat(self, messages: list[dict[str, str]], payload: dict[str, Any]) -> ChatResult:
        return ChatResult(content='{"ok": true}', prompt_tokens=7, completion_tokens=3)

    def embed(self, inputs: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in inputs]


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = config_from_defaults(SMALL)
        self.server = MinivikingServer(("127.0.0.1", 0), self.config, FakeRuntime())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def test_models_endpoint(self) -> None:
        payload = self._get("/v1/models?source=openviking")

        self.assertEqual(payload["object"], "list")
        self.assertEqual(len(payload["data"]), 2)

    def test_server_is_single_threaded_for_mlx_stream_safety(self) -> None:
        self.assertNotIsInstance(self.server, socketserver.ThreadingMixIn)

    def test_embeddings_endpoint(self) -> None:
        payload = self._post("/v1/embeddings", {"model": "ignored", "input": ["a", "b"]})

        self.assertEqual(payload["object"], "list")
        self.assertEqual(len(payload["data"]), 2)
        self.assertEqual(payload["data"][0]["embedding"], [0.1, 0.2, 0.3])

    def test_chat_completions_endpoint(self) -> None:
        payload = self._post(
            "/v1/chat/completions",
            {
                "model": "ignored",
                "messages": [{"role": "user", "content": "return json"}],
                "response_format": {"type": "json_object"},
            },
        )

        self.assertEqual(payload["object"], "chat.completion")
        self.assertEqual(payload["choices"][0]["message"]["content"], '{"ok": true}')

    def _get(self, path: str) -> dict[str, Any]:
        with urlopen(f"{self.base_url}{path}", timeout=2) as response:
            return json.loads(response.read())

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read())


if __name__ == "__main__":
    unittest.main()
