import tempfile
import unittest
from pathlib import Path

from miniviking.launchd import LABEL, plist_payload


class LaunchdTests(unittest.TestCase):
    def test_plist_payload_uses_user_launch_agent_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            payload = plist_payload(config_path)

        self.assertEqual(payload["Label"], LABEL)
        self.assertIs(payload["RunAtLoad"], True)
        self.assertIs(payload["KeepAlive"], True)
        self.assertEqual(payload["EnvironmentVariables"], {"MINIVIKING_CONFIG": str(config_path)})
        self.assertIn("miniviking-server", payload["ProgramArguments"])
        self.assertIn(str(config_path), payload["ProgramArguments"])


if __name__ == "__main__":
    unittest.main()
