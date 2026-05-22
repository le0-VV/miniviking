import json
import sys
import types
import unittest
from dataclasses import replace
from unittest.mock import patch

from miniviking.config import config_from_defaults
from miniviking.runtime import MlxRuntime
from miniviking.tiers import SMALL


class FakeArray:
    def __init__(self, rows: list[list[float]]) -> None:
        self.rows = rows

    def __truediv__(self, other: object) -> "FakeArray":
        return self

    def tolist(self) -> list[list[float]]:
        return self.rows


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

    def test_vlm_chat_uses_generation_result_text(self) -> None:
        config = config_from_defaults(replace(SMALL, llm_backend="mlx-vlm"))
        runtime = MlxRuntime(config)
        runtime._llm_model = types.SimpleNamespace(config={"model_type": "gemma4", "eos_token_id": 1})
        runtime._llm_processor = object()
        runtime._llm_vlm_config = runtime._llm_model.config
        calls: dict[str, object] = {}

        def fake_template(processor: object, config: object, messages: object, **kwargs: object) -> str:
            calls["messages"] = messages
            calls["template_kwargs"] = kwargs
            return "templated prompt"

        def fake_generate(*args: object, **kwargs: object) -> object:
            calls["generate_kwargs"] = kwargs
            return types.SimpleNamespace(text='{"ok": true}')

        fake_vlm = types.ModuleType("mlx_vlm")
        fake_vlm.generate = fake_generate
        fake_prompt_utils = types.ModuleType("mlx_vlm.prompt_utils")
        fake_prompt_utils.apply_chat_template = fake_template

        with patch.dict(sys.modules, {"mlx_vlm": fake_vlm, "mlx_vlm.prompt_utils": fake_prompt_utils}):
            result = runtime.chat([{"role": "user", "content": "hello"}], {})

        self.assertEqual(result.content, '{"ok": true}')
        self.assertEqual(calls["generate_kwargs"]["max_kv_size"], SMALL.max_kv_size)
        self.assertIsInstance(calls["messages"], list)

    def test_gemma_vlm_memory_adapter_compacts_and_repairs_memory_response(self) -> None:
        config = config_from_defaults(
            replace(SMALL, llm_backend="mlx-vlm", llm_model="mlx-community/gemma-4-e2b-it-4bit")
        )
        runtime = MlxRuntime(config)
        runtime._llm_model = types.SimpleNamespace(config={"model_type": "gemma4", "eos_token_id": 1})
        runtime._llm_processor = object()
        runtime._llm_vlm_config = runtime._llm_model.config
        calls: dict[str, object] = {}

        def fake_template(processor: object, config: object, messages: object, **kwargs: object) -> str:
            calls["messages"] = messages
            return "templated prompt"

        def fake_generate(*args: object, **kwargs: object) -> object:
            return types.SimpleNamespace(
                text=(
                    "```json\n"
                    '{"memories":[{"content":"I use Nix flakes for development.",'
                    '"metadata":{"kind":"preference","confidence":0.9,"source":"session"}},'
                    '{"content":"Run the tests before touching docs.",'
                    '"metadata":{"kind":"project","confidence":0.9,"source":"session"}}]}}\n'
                    "```"
                )
            )

        raw_prompt = (
            "You are the OpenViking memory extraction step.\n"
            "Example A transcript:\n"
            "User: Remember that Alice keeps a sourdough starter named Bubbles.\n"
            "Example A output:\n"
            '{"memories":[{"content":"Alice keeps a sourdough starter named Bubbles.",'
            '"metadata":{"kind":"profile","confidence":0.92,"source":"session"}}]}\n'
            "Now extract memories from this real transcript only:\n"
            "<transcript>\n"
            "User: For future Miniviking work, please remember that I use Nix flakes for development.\n"
            "Assistant: Noted.\n"
            "User: For this one debug session, run the tests before touching docs.\n"
            "</transcript>\n"
            'Return only JSON. If there are no durable memories, return {"memories":[]}.'
        )
        fake_vlm = types.ModuleType("mlx_vlm")
        fake_vlm.generate = fake_generate
        fake_prompt_utils = types.ModuleType("mlx_vlm.prompt_utils")
        fake_prompt_utils.apply_chat_template = fake_template

        with patch.dict(sys.modules, {"mlx_vlm": fake_vlm, "mlx_vlm.prompt_utils": fake_prompt_utils}):
            result = runtime.chat(
                [{"role": "system", "content": "miniviking system"}, {"role": "user", "content": raw_prompt}],
                {"response_format": {"type": "json_object"}},
            )

        generated_messages = calls["messages"]
        self.assertIsInstance(generated_messages, list)
        compact_prompt = generated_messages[1]["content"]
        self.assertIn("Nix flakes", compact_prompt)
        self.assertNotIn("sourdough", compact_prompt.lower())
        self.assertEqual(
            json.loads(result.content),
            {
                "memories": [
                    {
                        "content": "I use Nix flakes for development.",
                        "metadata": {"kind": "preference", "confidence": 0.9, "source": "session"},
                    }
                ]
            },
        )

    def test_embedding_model_accepts_inputs_parameter_variant(self) -> None:
        config = replace(config_from_defaults(SMALL), embedding=replace(config_from_defaults(SMALL).embedding, normalize=False))
        runtime = MlxRuntime(config)
        calls: dict[str, object] = {}

        class FakeTokenizer:
            def __call__(self, texts: list[str], **kwargs: object) -> dict[str, object]:
                calls["tokenizer_kwargs"] = kwargs
                return {"input_ids": "ids", "attention_mask": "mask"}

        class FakeEmbeddingModel:
            def __call__(self, inputs: object, attention_mask: object | None = None) -> object:
                calls["model_inputs"] = inputs
                calls["model_attention_mask"] = attention_mask
                return types.SimpleNamespace(text_embeds=FakeArray([[0.1, 0.2, 0.3]]))

        fake_mx = types.ModuleType("mlx.core")
        fake_mlx = types.ModuleType("mlx")
        fake_mlx.core = fake_mx

        runtime._embedding_model = FakeEmbeddingModel()
        runtime._embedding_tokenizer = FakeTokenizer()

        with patch.dict(sys.modules, {"mlx": fake_mlx, "mlx.core": fake_mx}):
            vectors = runtime.embed(["hello"])

        self.assertEqual(vectors, [[0.1, 0.2, 0.3]])
        self.assertEqual(calls["model_inputs"], "ids")
        self.assertEqual(calls["model_attention_mask"], "mask")

    def test_embedding_model_accepts_batch_encoding_variant(self) -> None:
        config = replace(config_from_defaults(SMALL), embedding=replace(config_from_defaults(SMALL).embedding, normalize=False))
        runtime = MlxRuntime(config)
        calls: dict[str, object] = {}

        class FakeBatchEncoding:
            data = {"input_ids": "ids", "attention_mask": "mask"}

        class FakeTokenizer:
            def __call__(self, texts: list[str], **kwargs: object) -> FakeBatchEncoding:
                return FakeBatchEncoding()

        class FakeEmbeddingModel:
            def __call__(self, inputs: object, attention_mask: object | None = None) -> object:
                calls["model_inputs"] = inputs
                calls["model_attention_mask"] = attention_mask
                return types.SimpleNamespace(text_embeds=FakeArray([[0.4, 0.5, 0.6]]))

        fake_mx = types.ModuleType("mlx.core")
        fake_mlx = types.ModuleType("mlx")
        fake_mlx.core = fake_mx

        runtime._embedding_model = FakeEmbeddingModel()
        runtime._embedding_tokenizer = FakeTokenizer()

        with patch.dict(sys.modules, {"mlx": fake_mlx, "mlx.core": fake_mx}):
            vectors = runtime.embed(["hello"])

        self.assertEqual(vectors, [[0.4, 0.5, 0.6]])
        self.assertEqual(calls["model_inputs"], "ids")
        self.assertEqual(calls["model_attention_mask"], "mask")


if __name__ == "__main__":
    unittest.main()
