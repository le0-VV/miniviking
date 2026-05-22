import unittest

from miniviking.config import config_from_defaults, config_from_payload
from miniviking.tiers import LARGE, MEDIUM, SMALL, defaults_for_memory, unified_memory_gib


class ConfigTests(unittest.TestCase):
    def test_defaults_for_memory_tiers(self) -> None:
        self.assertIs(defaults_for_memory(8), SMALL)
        self.assertIs(defaults_for_memory(11), SMALL)
        self.assertIs(defaults_for_memory(12), MEDIUM)
        self.assertIs(defaults_for_memory(16), MEDIUM)
        self.assertIs(defaults_for_memory(17), LARGE)
        self.assertEqual(SMALL.llm_backend, "mlx-lm")
        self.assertEqual(MEDIUM.llm_backend, "mlx-vlm")

    def test_embedding_model_uses_4bit_for_all_tiers(self) -> None:
        for tier in (SMALL, MEDIUM, LARGE):
            with self.subTest(tier=tier.name):
                self.assertEqual(tier.embedding_model, "mlx-community/embeddinggemma-300m-4bit")

    def test_unified_memory_rounding(self) -> None:
        self.assertEqual(unified_memory_gib(8 * 1024**3), 8)

    def test_tier_prompt_budget_covers_current_openviking_memory_prompt(self) -> None:
        for tier in (SMALL, MEDIUM, LARGE):
            with self.subTest(tier=tier.name):
                self.assertGreaterEqual(tier.max_kv_size, 8192)
                self.assertGreaterEqual(tier.max_prompt_tokens, 8192)

    def test_config_round_trip_payload(self) -> None:
        config = config_from_defaults(MEDIUM, mode="embedding", host="127.0.0.1", port=9999)
        payload = {
            "host": config.host,
            "port": config.port,
            "mode": config.mode,
            "tier": config.tier,
            "models": {
                "embedding_model": config.models.embedding_model,
                "llm_model": config.models.llm_model,
                "llm_backend": config.models.llm_backend,
                "embedding_dimensions": config.models.embedding_dimensions,
            },
            "generation": {
                "temperature": config.generation.temperature,
                "max_kv_size": config.generation.max_kv_size,
                "max_prompt_tokens": config.generation.max_prompt_tokens,
                "max_tokens": config.generation.max_tokens,
            },
            "embedding": {
                "batch_size": config.embedding.batch_size,
                "normalize": config.embedding.normalize,
                "max_input_tokens": config.embedding.max_input_tokens,
            },
        }

        loaded = config_from_payload(payload)

        self.assertEqual(loaded, config)


if __name__ == "__main__":
    unittest.main()
