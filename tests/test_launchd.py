import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from miniviking.launchd import LABEL, UTF8_ENVIRONMENT, plist_payload


class LaunchdTests(unittest.TestCase):
    def test_plist_payload_uses_user_launch_agent_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            miniviking_binary = Path(tmpdir) / "miniviking"
            server_binary = Path(tmpdir) / "miniviking-server"
            miniviking_binary.touch()
            server_binary.touch()
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("miniviking.processes.sys.executable", str(miniviking_binary)),
            ):
                payload = plist_payload(config_path)

        self.assertEqual(payload["Label"], LABEL)
        self.assertIs(payload["RunAtLoad"], True)
        self.assertIs(payload["KeepAlive"], True)
        self.assertEqual(
            payload["EnvironmentVariables"],
            {"MINIVIKING_CONFIG": str(config_path), **UTF8_ENVIRONMENT},
        )
        self.assertEqual(payload["ProgramArguments"][0], str(server_binary))
        self.assertIn(str(config_path), payload["ProgramArguments"])


if __name__ == "__main__":
    unittest.main()
