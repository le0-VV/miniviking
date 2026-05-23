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
    def test_install_defaults_to_embedding_only_below_12gb(self) -> None:
        for memory_gib in (8, 11):
            with self.subTest(memory_gib=memory_gib), tempfile.TemporaryDirectory() as tmpdir:
                config_path = Path(tmpdir) / "config.json"
                stdout = io.StringIO()
                stderr = io.StringIO()

                with (
                    patch("miniviking.cli.download_models") as download_models,
                    patch("miniviking.cli.write_plist") as write_plist,
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    main(["install", "--memory-gib", str(memory_gib), "--config", str(config_path), "--skip-launch-agent"])

                config = load_config(config_path)
                downloaded_config = download_models.call_args.args[0]
                self.assertEqual(config.mode, "embedding")
                self.assertFalse(downloaded_config.llm_enabled)
                self.assertTrue(downloaded_config.embedding_enabled)
                self.assertIn("Runtime mode: embedding", stdout.getvalue())
                self.assertIn("Local LLM serving is not supported below 12 GB", stderr.getvalue())
                write_plist.assert_not_called()

    def test_install_defaults_to_both_at_12gb(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            stdout = io.StringIO()

            with (
                patch("miniviking.cli.download_models") as download_models,
                patch("miniviking.cli.write_plist"),
                redirect_stdout(stdout),
                redirect_stderr(io.StringIO()),
            ):
                main(["install", "--memory-gib", "12", "--config", str(config_path), "--skip-launch-agent"])

            config = load_config(config_path)
            downloaded_config = download_models.call_args.args[0]
            self.assertEqual(config.mode, "both")
            self.assertTrue(downloaded_config.llm_enabled)
            self.assertTrue(downloaded_config.embedding_enabled)
            self.assertIn("Runtime mode: both", stdout.getvalue())

    def test_install_rejects_llm_modes_below_12gb(self) -> None:
        for memory_gib in (8, 11):
            for mode in ("llm", "both"):
                with self.subTest(memory_gib=memory_gib, mode=mode), tempfile.TemporaryDirectory() as tmpdir:
                    config_path = Path(tmpdir) / "config.json"
                    stderr = io.StringIO()

                    with (
                        patch("miniviking.cli.download_models") as download_models,
                        patch("miniviking.cli.write_plist") as write_plist,
                        redirect_stdout(io.StringIO()),
                        redirect_stderr(stderr),
                    ):
                        with self.assertRaises(SystemExit) as raised:
                            main(
                                [
                                    "install",
                                    "--memory-gib",
                                    str(memory_gib),
                                    "--mode",
                                    mode,
                                    "--config",
                                    str(config_path),
                                    "--skip-launch-agent",
                                ]
                            )

                    self.assertEqual(raised.exception.code, 1)
                    self.assertIn("Machines below 12 GB are embedding-only", stderr.getvalue())
                    self.assertFalse(config_path.exists())
                    download_models.assert_not_called()
                    write_plist.assert_not_called()

    def test_install_can_skip_launch_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            stdout = io.StringIO()

            with (
                patch("miniviking.cli.download_models") as download_models,
                patch("miniviking.cli.write_plist") as write_plist,
                redirect_stdout(stdout),
                redirect_stderr(io.StringIO()),
            ):
                main(
                    [
                        "install",
                        "--memory-gib",
                        "12",
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
            download_models.assert_called_once()
            write_plist.assert_not_called()

    def test_setup_preserves_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            with (
                patch("miniviking.cli.download_models"),
                patch("miniviking.cli.write_plist"),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                main(
                    [
                        "install",
                        "--memory-gib",
                        "12",
                        "--mode",
                        "embedding",
                        "--port",
                        "9000",
                        "--config",
                        str(config_path),
                        "--skip-launch-agent",
                    ]
                )

            stdout = io.StringIO()
            with (
                patch("miniviking.cli.download_models") as download_models,
                patch("miniviking.cli.write_plist") as write_plist,
                redirect_stdout(stdout),
                redirect_stderr(io.StringIO()),
            ):
                main(
                    [
                        "setup",
                        "--memory-gib",
                        "16",
                        "--mode",
                        "both",
                        "--port",
                        "9999",
                        "--config",
                        str(config_path),
                        "--skip-launch-agent",
                        "--preserve-existing-config",
                    ]
                )

            config = load_config(config_path)
            downloaded_config = download_models.call_args.args[0]
            self.assertEqual(config.mode, "embedding")
            self.assertEqual(config.port, 9000)
            self.assertEqual(downloaded_config.mode, "embedding")
            self.assertEqual(downloaded_config.port, 9000)
            self.assertIn("Using existing config", stdout.getvalue())
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
                main(["install", "--memory-gib", "12", "--mode", "llm", "--config", str(config_path), "--skip-launch-agent"])

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
                main(["install", "--memory-gib", "12", "--mode", "both", "--config", str(config_path), "--skip-launch-agent"])

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
                main(["install", "--memory-gib", "12", "--mode", "both", "--config", str(config_path), "--skip-launch-agent"])

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
