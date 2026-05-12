import unittest

from miniviking.config import config_from_defaults
from miniviking.runtime import MlxRuntime
from miniviking.tiers import SMALL


class RuntimeSafetyTests(unittest.TestCase):
    def test_chat_rejects_nonzero_temperature(self) -> None:
        runtime = MlxRuntime(config_from_defaults(SMALL))
        runtime._llm_model = object()

        with self.assertRaisesRegex(ValueError, "temperature=0.0"):
            runtime.chat([{"role": "user", "content": "hello"}], {"temperature": 0.2})

    def test_chat_rejects_excessive_max_tokens(self) -> None:
        runtime = MlxRuntime(config_from_defaults(SMALL))
        runtime._llm_model = object()

        with self.assertRaisesRegex(ValueError, "max_tokens exceeds"):
            runtime.chat([{"role": "user", "content": "hello"}], {"max_tokens": SMALL.max_tokens + 1})


if __name__ == "__main__":
    unittest.main()
