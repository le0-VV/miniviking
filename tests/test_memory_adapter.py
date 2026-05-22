import json
import unittest

from miniviking.memory_adapter import (
    compile_memory_prompt,
    extract_real_transcript,
    filter_memory_payload,
    finalize_memory_response,
    maybe_adapt_openviking_memory_request,
    normalize_memory_payload,
    repair_memory_json,
)


def memory_prompt(transcript: str) -> str:
    return (
        "You are the OpenViking memory extraction step.\n"
        "Example A transcript:\n"
        "User: Remember that Alice keeps a sourdough starter named Bubbles.\n"
        "Example A output:\n"
        '{"memories":[{"content":"Alice keeps a sourdough starter named Bubbles.",'
        '"metadata":{"kind":"profile","confidence":0.92,"source":"session"}}]}\n\n'
        "Now extract memories from this real transcript only:\n"
        "<transcript>\n"
        f"{transcript}\n"
        "</transcript>\n"
        'Return only JSON. If there are no durable memories, return {"memories":[]}.'
    )


def openviking_v1_prompt(conversation: str) -> str:
    return (
        "Analyze the following session context and extract memories worth long-term preservation.\n\n"
        "## Recent Conversation\n"
        f"{conversation}\n\n"
        "## Important Processing Rules\n"
        "- Read and analyze the full conversation from start to end before deciding outputs.\n\n"
        "# Output Format\n"
        "Please return JSON format:\n"
        '{"memories":[{"category":"preferences","abstract":"...","overview":"...","content":"..."}]}\n'
        'If nothing worth recording, return {"memories": []}'
    )


def memory(content: str, kind: str = "project") -> dict[str, object]:
    return {"content": content, "metadata": {"kind": kind, "confidence": 0.9, "source": "session"}}


class MemoryAdapterTests(unittest.TestCase):
    def test_detector_triggers_on_openviking_memory_json_request(self) -> None:
        transcript = "User: Please remember that I use Nix flakes for development."
        request = maybe_adapt_openviking_memory_request(
            [
                {"role": "system", "content": "miniviking system"},
                {"role": "user", "content": memory_prompt(transcript)},
            ],
            {"response_format": {"type": "json_object"}},
            model_id="mlx-community/gemma-4-e2b-it-4bit",
            llm_backend="mlx-vlm",
            enabled=True,
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.messages[0], {"role": "system", "content": "miniviking system"})
        self.assertIn("Nix flakes", request.messages[1]["content"])

    def test_detector_triggers_on_stock_openviking_prompt_json_instruction(self) -> None:
        transcript = "User: Please remember that I prefer source-build Homebrew formulas."
        request = maybe_adapt_openviking_memory_request(
            [
                {"role": "system", "content": "miniviking system"},
                {"role": "user", "content": memory_prompt(transcript)},
            ],
            {},
            model_id="mlx-community/gemma-4-e2b-it-4bit",
            llm_backend="mlx-vlm",
            enabled=True,
        )

        self.assertIsNotNone(request)

    def test_detector_triggers_on_stock_openviking_v1_prompt_shape(self) -> None:
        request = maybe_adapt_openviking_memory_request(
            [
                {"role": "system", "content": "miniviking system"},
                {
                    "role": "user",
                    "content": openviking_v1_prompt("[user]: Please remember that I use Nix flakes."),
                },
            ],
            {},
            model_id="mlx-community/gemma-4-e2b-it-4bit",
            llm_backend="mlx-vlm",
            enabled=True,
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertIn("[user]: Please remember that I use Nix flakes.", request.messages[1]["content"])
        self.assertNotIn("Important Processing Rules", request.messages[1]["content"])

    def test_detector_ignores_ordinary_json_requests(self) -> None:
        request = maybe_adapt_openviking_memory_request(
            [
                {"role": "system", "content": "miniviking system"},
                {"role": "user", "content": "Return JSON with a memories array describing this API response."},
            ],
            {"response_format": {"type": "json_object"}},
            model_id="mlx-community/gemma-4-e2b-it-4bit",
            llm_backend="mlx-vlm",
            enabled=True,
        )

        self.assertIsNone(request)

    def test_prompt_compiler_uses_real_transcript_not_few_shot_examples(self) -> None:
        transcript = "User: Please remember that my checkout is /Users/leonardw/Projects/miniviking."
        raw_prompt = memory_prompt(transcript)

        real_transcript = extract_real_transcript([{"role": "user", "content": raw_prompt}])
        compiled = compile_memory_prompt(real_transcript)

        self.assertIn("/Users/leonardw/Projects/miniviking", compiled)
        self.assertNotIn("sourdough", compiled.lower())
        self.assertNotIn("Alice keeps", compiled)

    def test_json_repair_handles_fences_trailing_text_and_extra_brace(self) -> None:
        cases = [
            '```json\n{"memories":[]}\n```',
            '{"memories":[]}.',
            '{"memories":[]}}',
        ]

        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_memory_payload(repair_memory_json(raw)), {"memories": []})

    def test_normalization_drops_malformed_memory_items(self) -> None:
        parsed = {
            "memories": [
                memory("I prefer concise engineering answers.", "preference"),
                {"content": "missing metadata"},
                memory("invalid kind", "instruction"),
            ]
        }

        normalized = normalize_memory_payload(parsed)

        self.assertEqual(normalized, {"memories": [memory("I prefer concise engineering answers.", "preference")]})

    def test_post_filter_drops_assistant_only_facts(self) -> None:
        transcript = (
            "User: What does port 8745 mean in this config?\n"
            "Assistant: It is the default local Miniviking port.\n"
            "User: Thanks."
        )
        payload = {"memories": [memory("The default local Miniviking port is 8745.", "environment")]}

        self.assertEqual(filter_memory_payload(payload, transcript), {"memories": []})

    def test_post_filter_drops_transient_commands(self) -> None:
        transcript = (
            "User: For future Miniviking work, remember that I use Nix flakes.\n"
            "Assistant: Noted.\n"
            "User: For this one debug session, run the tests before touching docs."
        )
        payload = {
            "memories": [
                memory("I use Nix flakes for Miniviking work.", "preference"),
                memory("Run the tests before touching docs.", "project"),
            ]
        }

        filtered = filter_memory_payload(payload, transcript)

        self.assertEqual(filtered["memories"], [memory("I use Nix flakes for Miniviking work.", "preference")])

    def test_post_filter_drops_negative_and_corrected_facts(self) -> None:
        transcript = (
            "User: Please remember that my default Miniviking branch prefix is codex/ "
            "and that I want Homebrew formula changes kept source-build only.\n"
            "Assistant: Saved.\n"
            "User: Also, correction: don't remember the branch prefix. That was only "
            "for today's experiment. Keep the Homebrew source-build constraint."
        )
        payload = {
            "memories": [
                memory("Do not remember the branch prefix codex/.", "project"),
                memory("The user's default Miniviking branch prefix is codex/.", "project"),
                memory("Homebrew formula changes are kept source-build only.", "project"),
            ]
        }

        filtered = filter_memory_payload(payload, transcript)

        self.assertEqual(filtered["memories"], [memory("Homebrew formula changes are kept source-build only.", "project")])

    def test_finalize_outputs_normalized_json(self) -> None:
        raw = (
            "```json\n"
            '{"memories":[{"content":"I prefer concise engineering answers.",'
            '"metadata":{"kind":"preference","confidence":0.9,"source":"session","ignored":true}}]}}\n'
            "```"
        )
        transcript = "User: Please remember that I prefer concise engineering answers."

        content = finalize_memory_response(raw, transcript)

        self.assertEqual(
            json.loads(content),
            {"memories": [memory("I prefer concise engineering answers.", "preference")]}
        )


if __name__ == "__main__":
    unittest.main()
