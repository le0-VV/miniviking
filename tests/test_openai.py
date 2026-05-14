import unittest

from miniviking.openai import ApiError, chat_completion_response, normalize_messages, validate_json_content


class OpenAITests(unittest.TestCase):
    def test_normalize_messages_prepends_miniviking_system_prompt(self) -> None:
        messages = normalize_messages([{"role": "user", "content": "extract memory"}])

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("valid JSON", messages[0]["content"])
        self.assertIn("Never copy sample content", messages[0]["content"])
        self.assertEqual(messages[1], {"role": "user", "content": "extract memory"})

    def test_validate_json_content_fails_fast(self) -> None:
        with self.assertRaises(ApiError):
            validate_json_content("not json")

    def test_chat_completion_response_shape(self) -> None:
        response = chat_completion_response(
            model="model-id",
            content='{"ok": true}',
            prompt_tokens=10,
            completion_tokens=3,
        )

        self.assertEqual(response["object"], "chat.completion")
        self.assertEqual(response["choices"][0]["message"]["content"], '{"ok": true}')
        self.assertEqual(response["usage"]["total_tokens"], 13)


if __name__ == "__main__":
    unittest.main()
