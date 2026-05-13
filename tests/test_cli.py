import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from miniviking.cli import main
from miniviking.config import load_config


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


if __name__ == "__main__":
    unittest.main()
