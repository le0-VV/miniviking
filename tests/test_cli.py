import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from miniviking.cli import main
from miniviking.config import load_config
from miniviking.selftest import ServerTestCheck


class CliTests(unittest.TestCase):
    def test_install_can_skip_launch_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                patch("miniviking.cli.download_models") as download_models,
                patch("miniviking.cli.write_plist") as write_plist,
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                main(
                    [
                        "install",
                        "--memory-gib",
                        "8",
                        "--mode",
                        "llm",
                        "--config",
                        str(config_path),
                        "--skip-launch-agent",
                    ]
                )

            config = load_config(config_path)
            self.assertEqual(config.mode, "llm")
            self.assertIn("Skipped LaunchAgent install", stdout.getvalue())
            self.assertIn("not ideal", stderr.getvalue())
            download_models.assert_called_once()
            write_plist.assert_not_called()

    def test_serve_alias_runs_process_supervisor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            with (
                patch("miniviking.cli.download_models"),
                patch("miniviking.cli.write_plist"),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                main(["install", "--memory-gib", "8", "--mode", "llm", "--config", str(config_path), "--skip-launch-agent"])

            with patch("miniviking.cli.serve_processes") as serve_processes:
                main(["serve", "--config", str(config_path)])

            serve_processes.assert_called_once()

    def test_worker_commands_load_configured_worker_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            with (
                patch("miniviking.cli.download_models"),
                patch("miniviking.cli.write_plist"),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                main(["install", "--memory-gib", "8", "--mode", "both", "--config", str(config_path), "--skip-launch-agent"])

            with patch("miniviking.cli.serve_llm_worker") as serve_llm_worker:
                main(["miniviking-llm", "--config", str(config_path), "--host", "127.0.0.1", "--port", "9001"])

            with patch("miniviking.cli.serve_embedding_worker") as serve_embedding_worker:
                main(["miniviking-embed", "--config", str(config_path), "--host", "127.0.0.1", "--port", "9002"])

            serve_llm_worker.assert_called_once()
            serve_embedding_worker.assert_called_once()

    def test_test_command_runs_server_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            with (
                patch("miniviking.cli.download_models"),
                patch("miniviking.cli.write_plist"),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                main(["install", "--memory-gib", "8", "--mode", "both", "--config", str(config_path), "--skip-launch-agent"])

            stdout = io.StringIO()
            with (
                patch("miniviking.cli.run_server_tests", return_value=[ServerTestCheck("health", True, "server is ready")]) as run_server_tests,
                redirect_stdout(stdout),
            ):
                main(["test", "--config", str(config_path), "--skip-chat"])

            run_server_tests.assert_called_once()
            self.assertIn("ok: health: server is ready", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
