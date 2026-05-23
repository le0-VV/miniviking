import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from miniviking.config import config_from_defaults
from miniviking.processes import (
    EMBED_ROLE,
    LLM_ROLE,
    WorkerRuntime,
    WorkerServer,
    embedding_worker_port,
    llm_worker_port,
    server_program_arguments,
    validate_llm_supported_for_host,
    worker_command,
)
from miniviking.runtime import ChatResult
from miniviking.tiers import SMALL


class FakeRuntime:
    def load(self) -> None:
        return

    def chat(self, messages: list[dict[str, str]], payload: dict[str, object]) -> ChatResult:
        return ChatResult(content='{"ok": true}', prompt_tokens=5, completion_tokens=3)

    def embed(self, inputs: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in inputs]


class ProcessTests(unittest.TestCase):
    def test_worker_ports_are_derived_from_public_port(self) -> None:
        config = config_from_defaults(SMALL, port=9000)

        self.assertEqual(llm_worker_port(config), 9001)
        self.assertEqual(embedding_worker_port(config), 9002)

    def test_worker_command_prefers_native_role_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            server_binary = Path(tmpdir) / "miniviking-server"
            llm_binary = Path(tmpdir) / LLM_ROLE
            server_binary.touch()
            llm_binary.touch()
            config_path = Path(tmpdir) / "config.json"

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("miniviking.processes.sys.executable", str(server_binary)),
            ):
                command = worker_command(LLM_ROLE, config_path=config_path, host="127.0.0.1", port=9001)

        self.assertIsNone(command.executable)
        self.assertEqual(command.args[:2], [str(llm_binary), "--config"])
        self.assertIn(str(config_path), command.args)

    def test_worker_command_falls_back_to_single_binary_with_role_argv0(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            binary = str(Path(tmpdir) / "miniviking")
            config_path = Path(tmpdir) / "config.json"

            with patch.dict(os.environ, {"MINIVIKING_BINARY": binary}, clear=True):
                command = worker_command(LLM_ROLE, config_path=config_path, host="127.0.0.1", port=9001)

        self.assertEqual(command.executable, binary)
        self.assertEqual(command.args[:2], [LLM_ROLE, LLM_ROLE])
        self.assertIn(str(config_path), command.args)

    def test_server_program_arguments_prefers_native_server_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            miniviking_binary = Path(tmpdir) / "miniviking"
            server_binary = Path(tmpdir) / "miniviking-server"
            miniviking_binary.touch()
            server_binary.touch()
            config_path = Path(tmpdir) / "config.json"

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("miniviking.processes.sys.executable", str(miniviking_binary)),
            ):
                arguments = server_program_arguments(config_path)

        self.assertEqual(arguments, [str(server_binary), "--config", str(config_path)])

    def test_worker_runtime_proxies_chat_and_embeddings(self) -> None:
        llm_server, llm_thread = self._start_worker(LLM_ROLE)
        embedding_server, embedding_thread = self._start_worker(EMBED_ROLE)
        try:
            runtime = WorkerRuntime(
                llm_url=f"http://127.0.0.1:{llm_server.server_port}",
                embedding_url=f"http://127.0.0.1:{embedding_server.server_port}",
            )

            chat = runtime.chat([{"role": "user", "content": "hello"}], {"temperature": 0.0})
            embeddings = runtime.embed(["a", "b"])

            self.assertEqual(chat.content, '{"ok": true}')
            self.assertEqual(embeddings, [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]])
        finally:
            self._stop_worker(llm_server, llm_thread)
            self._stop_worker(embedding_server, embedding_thread)

    def test_worker_health_reports_role(self) -> None:
        server, thread = self._start_worker(LLM_ROLE)
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/health", timeout=2) as response:
                payload = json.loads(response.read())
        finally:
            self._stop_worker(server, thread)

        self.assertEqual(payload, {"status": "ok", "role": LLM_ROLE})

    def test_llm_runtime_guard_rejects_hosts_below_12gb(self) -> None:
        config = config_from_defaults(SMALL, mode="llm")

        with self.assertRaisesRegex(RuntimeError, "below 12 GB"):
            validate_llm_supported_for_host(config, memory_gib=11)

    def test_llm_runtime_guard_allows_embedding_only_below_12gb(self) -> None:
        config = config_from_defaults(SMALL, mode="embedding")

        validate_llm_supported_for_host(config, memory_gib=8)

    def _start_worker(self, role: str) -> tuple[WorkerServer, threading.Thread]:
        server = WorkerServer(("127.0.0.1", 0), config_from_defaults(SMALL), role, FakeRuntime())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _stop_worker(self, server: WorkerServer, thread: threading.Thread) -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
