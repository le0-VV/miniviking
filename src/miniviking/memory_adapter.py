from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

ALLOWED_MEMORY_KINDS = {"preference", "profile", "project", "environment"}

MEMORY_SCHEMA_SHAPE = (
    '{"memories":[{"content":"...","metadata":{"kind":"preference|profile|project|environment",'
    '"confidence":0.9,"source":"session"}}]}'
)

TRANSCRIPT_TAG_RE = re.compile(r"<transcript>\s*(.*?)\s*</transcript>", re.IGNORECASE | re.DOTALL)
ROLE_LINE_RE = re.compile(r"^\s*(?:\[\d+\])?\s*\[?(user|assistant|system|tool)\]?\s*:\s*(.*)$", re.IGNORECASE)

STOPWORDS = {
    "about",
    "actually",
    "after",
    "again",
    "also",
    "anything",
    "before",
    "being",
    "check",
    "could",
    "details",
    "does",
    "fact",
    "facts",
    "from",
    "future",
    "keep",
    "latest",
    "memory",
    "memories",
    "noted",
    "only",
    "please",
    "prefer",
    "remember",
    "save",
    "saved",
    "says",
    "session",
    "setup",
    "should",
    "that",
    "their",
    "there",
    "this",
    "today",
    "understood",
    "user",
    "what",
    "when",
    "with",
}

NEGATIVE_MEMORY_PHRASES = (
    "do not remember",
    "don't remember",
    "dont remember",
    "not remember",
    "do not save",
    "don't save",
    "dont save",
    "not save",
    "not to save",
    "do not store",
    "don't store",
    "dont store",
    "not store",
    "throwaway",
)

TEMPORARY_MEMORY_PHRASES = (
    "for this one",
    "one debug session",
    "debug session",
    "run the tests before touching docs",
    "before touching docs",
    "for this session",
    "this session",
    "today's experiment",
    "todays experiment",
    "temporary",
    "one-off",
    "throwaway",
    "for now",
)

NO_MEMORY_REQUEST_PHRASES = (
    "do not save anything",
    "don't save anything",
    "dont save anything",
    "do not remember anything",
    "don't remember anything",
    "dont remember anything",
    "do not save any memories",
    "don't save any memories",
    "dont save any memories",
    "nothing to remember",
)

NEGATED_SUBJECT_INTROS = (
    "do not remember",
    "don't remember",
    "dont remember",
    "do not save",
    "don't save",
    "dont save",
    "not remember",
    "not save",
    "not to save",
)


@dataclass(frozen=True)
class OpenVikingMemoryRequest:
    messages: list[dict[str, str]]
    transcript: str
    output_format: str = "memory_payload"


class MemoryAdapterError(RuntimeError):
    pass


def default_memory_adapter_enabled(model_id: str, llm_backend: str) -> bool:
    return llm_backend == "mlx-vlm" and "gemma-4-" in model_id.lower()


def maybe_adapt_openviking_memory_request(
    messages: list[dict[str, str]],
    payload: dict[str, Any],
    *,
    model_id: str,
    llm_backend: str,
    enabled: bool,
) -> OpenVikingMemoryRequest | None:
    if not enabled or not default_memory_adapter_enabled(model_id, llm_backend):
        return None
    combined_text = "\n".join(message.get("content", "") for message in messages)
    is_v2_request = looks_like_openviking_v2_memory_request(combined_text, payload)
    if not is_v2_request and not _payload_wants_json(payload) and not _prompt_requests_json(combined_text):
        return None

    if not is_v2_request and not looks_like_openviking_memory_request(combined_text, payload):
        return None

    transcript = extract_real_transcript(messages)
    if not transcript.strip():
        return None

    adapted_messages: list[dict[str, str]] = []
    if messages and messages[0].get("role") == "system":
        adapted_messages.append(messages[0])
    adapted_messages.append({"role": "user", "content": compile_memory_prompt(transcript)})
    return OpenVikingMemoryRequest(
        messages=adapted_messages,
        transcript=transcript,
        output_format="openviking_v2" if is_v2_request else "memory_payload",
    )


def looks_like_openviking_memory_request(text: str, payload: dict[str, Any]) -> bool:
    lowered = text.lower()
    response_format_text = json.dumps(payload.get("response_format", {}), sort_keys=True).lower()
    has_memory_schema = '"memories"' in response_format_text or "memories" in lowered
    asks_for_extraction = "extract" in lowered and ("memory" in lowered or "memories" in lowered)
    has_source_marker = any(marker in lowered for marker in ("transcript", "conversation", "session"))
    has_openviking_marker = any(
        marker in lowered
        for marker in (
            "openviking",
            "viking://user/memories",
            "long-term memories",
            "long-term preservation",
            "memory extraction",
            "session context and extract memories",
        )
    )
    return has_memory_schema and asks_for_extraction and has_source_marker and has_openviking_marker


def looks_like_openviking_v2_memory_request(text: str, payload: dict[str, Any]) -> bool:
    if not payload_uses_tools(payload):
        return False
    lowered = text.lower()
    tool_text = json.dumps(payload.get("tools", []), sort_keys=True).lower()
    haystack = f"{lowered}\n{tool_text}"
    has_conversation = any(
        marker in lowered
        for marker in (
            "conversation history",
            "session time",
            "relative times",
            "[0][user]",
            "[user]",
        )
    )
    has_memory_task = any(
        marker in haystack
        for marker in (
            "memory extraction agent",
            "update memories",
            "memory write/edit/delete operations",
            "available memory types",
            "memory_type",
            "memories/",
        )
    )
    has_operations_schema = any(
        marker in haystack
        for marker in (
            "delete_uris",
            "page_id",
            "profile",
            "preferences",
            "entities",
            "events",
        )
    )
    return has_conversation and has_memory_task and has_operations_schema


def payload_uses_tools(payload: dict[str, Any]) -> bool:
    tools = payload.get("tools")
    return isinstance(tools, list) and len(tools) > 0


def compile_memory_prompt(transcript: str) -> str:
    transcript = transcript.strip()
    return (
        "Extract durable long-term memories from the transcript.\n"
        "Save only explicit stable facts stated by the user for future context.\n"
        "Save stable preferences, project facts, environment facts, and profile facts.\n"
        "Discard assistant explanations, temporary instructions, examples, thanks, troubleshooting details, "
        "and corrected facts.\n"
        "If the user says not to remember a fact, omit that fact entirely; do not save a negative memory "
        "about not remembering it.\n"
        "Latest corrections override older statements.\n"
        "Return valid JSON only. The whole response must be one object with one key, memories.\n"
        "Each memory item must be an object with content and metadata. The final characters must be ]}.\n"
        f"Shape: {MEMORY_SCHEMA_SHAPE}\n"
        'If there are no durable memories, return {"memories":[]}.\n\n'
        "Transcript:\n"
        f"{transcript}"
    )


def extract_real_transcript(messages: list[dict[str, str]]) -> str:
    text = "\n".join(message.get("content", "") for message in messages if message.get("role") != "system")
    tagged = TRANSCRIPT_TAG_RE.findall(text)
    if tagged:
        return _clean_transcript(tagged[-1])

    lowered = text.lower()
    for marker in (
        "now extract memories from this real transcript only:",
        "extract memories from this real transcript only:",
        "real transcript:",
        "transcript:",
        "## conversation history",
        "## recent conversation",
    ):
        index = lowered.rfind(marker)
        if index >= 0:
            candidate = text[index + len(marker) :]
            return _clean_transcript(_strip_conversation_metadata(_strip_trailing_prompt_instructions(candidate)))

    turns = _transcript_turns(text)
    if turns:
        return "\n".join(f"{role.title()}: {content}" for role, content in turns if role in {"user", "assistant"})
    return text.strip()


def repair_memory_json(content: str) -> Any:
    stripped = _strip_markdown_fence(content.strip())
    parsed = _raw_decode_first_object(stripped)
    if parsed is not None:
        return parsed

    for index in reversed([idx for idx, char in enumerate(stripped) if char == "}"]):
        candidate = stripped[:index] + stripped[index + 1 :]
        parsed = _raw_decode_first_object(candidate)
        if parsed is not None:
            return parsed

    raise MemoryAdapterError("model did not return repairable memory JSON")


def normalize_memory_payload(parsed: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(parsed, dict) or "memories" not in parsed:
        raise MemoryAdapterError("model memory JSON did not contain a memories object")
    raw_memories = parsed.get("memories")
    if not isinstance(raw_memories, list):
        raise MemoryAdapterError("model memory JSON memories value was not an array")

    memories: list[dict[str, Any]] = []
    for raw_memory in raw_memories:
        normalized = _normalize_memory(raw_memory)
        if normalized is not None:
            memories.append(normalized)
    return {"memories": memories}


def filter_memory_payload(payload: dict[str, list[dict[str, Any]]], transcript: str) -> dict[str, list[dict[str, Any]]]:
    turns = _transcript_turns(transcript)
    if _latest_user_requests_no_memories(turns):
        return {"memories": []}

    user_text = "\n".join(content for role, content in turns if role == "user")
    assistant_text = "\n".join(content for role, content in turns if role == "assistant")
    negated_subjects = _negated_subjects(turns)

    filtered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for memory in payload["memories"]:
        content = memory["content"].strip()
        content_key = content.casefold()
        if content_key in seen:
            continue
        if _is_negative_memory(content):
            continue
        if _is_temporary_memory(content):
            continue
        if _matches_negated_subject(content, negated_subjects):
            continue
        if _sourced_only_from_assistant(content, user_text, assistant_text):
            continue
        seen.add(content_key)
        filtered.append({"content": content, "metadata": memory["metadata"]})
    return {"memories": filtered}


def finalize_memory_response(content: str, transcript: str, output_format: str = "memory_payload") -> str:
    parsed = repair_memory_json(content)
    normalized = normalize_memory_payload(parsed)
    filtered = filter_memory_payload(normalized, transcript)
    if output_format == "openviking_v2":
        filtered = memory_payload_to_openviking_v2_operations(filtered)
    return json.dumps(filtered, separators=(",", ":"), ensure_ascii=False)


def memory_payload_to_openviking_v2_operations(payload: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    operations: dict[str, Any] = {
        "profile": [],
        "preferences": [],
        "entities": [],
        "events": [],
        "tools": [],
        "skills": [],
        "delete_uris": [],
    }
    profile_items: list[str] = []
    next_page_id = 100

    for memory in payload["memories"]:
        content = memory["content"]
        kind = memory["metadata"]["kind"]
        if kind == "profile":
            profile_items.append(f"- {content}")
        elif kind == "preference":
            operations["preferences"].append(
                {
                    "page_id": next_page_id,
                    "user": "default",
                    "topic": _topic_from_content(content),
                    "content": content,
                }
            )
            next_page_id += 1
        elif kind in {"project", "environment"}:
            operations["entities"].append(
                {
                    "page_id": next_page_id,
                    "category": "projects" if kind == "project" else "environment",
                    "name": _entity_name_from_content(content),
                    "content": content,
                }
            )
            next_page_id += 1

    if profile_items:
        operations["profile"] = [{"page_id": next_page_id, "content": "\n".join(profile_items)}]
    return operations


def _payload_wants_json(payload: dict[str, Any]) -> bool:
    response_format = payload.get("response_format")
    return isinstance(response_format, dict) and response_format.get("type") in {"json_object", "json_schema"}


def _prompt_requests_json(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "return only json",
            "only output json",
            "output json",
            "return json format",
            "please return json",
            '{"memories"',
            '"memories"',
        )
    )


def _clean_transcript(transcript: str) -> str:
    return transcript.strip().strip("`").strip()


def _strip_trailing_prompt_instructions(text: str) -> str:
    stops = (
        "\nAfter exploring",
        "\nReturn only JSON",
        "\nReturn valid JSON",
        "\nOutput JSON",
        "\nExample output",
        "\n## Important Processing Rules",
        "\n# Memory Extraction Criteria",
    )
    candidate = text
    lowered = candidate.lower()
    for stop in stops:
        index = lowered.find(stop.lower())
        if index >= 0:
            candidate = candidate[:index]
            break
    return candidate


def _strip_conversation_metadata(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("**Session Time:**"):
            continue
        if stripped.startswith("Relative times "):
            continue
        lines.append(line)
    return "\n".join(lines)


def _strip_markdown_fence(content: str) -> str:
    if not content.startswith("```"):
        return content
    lines = content.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```"):
        if lines[-1].strip().startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
    return "\n".join(lines).strip()


def _raw_decode_first_object(content: str) -> Any | None:
    start = content.find("{")
    if start < 0:
        return None
    decoder = json.JSONDecoder()
    try:
        parsed, _ = decoder.raw_decode(content[start:])
    except json.JSONDecodeError:
        return None
    return parsed


def _normalize_memory(raw_memory: Any) -> dict[str, Any] | None:
    if not isinstance(raw_memory, dict):
        return None
    content = raw_memory.get("content")
    metadata = raw_memory.get("metadata")
    if not isinstance(content, str) or not content.strip() or not isinstance(metadata, dict):
        return None

    kind = metadata.get("kind")
    source = metadata.get("source")
    confidence = metadata.get("confidence")
    if not isinstance(kind, str) or kind not in ALLOWED_MEMORY_KINDS:
        return None
    if source != "session":
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        return None

    confidence_value = max(0.0, min(1.0, float(confidence)))
    return {
        "content": content.strip(),
        "metadata": {"kind": kind, "confidence": confidence_value, "source": "session"},
    }


def _transcript_turns(transcript: str) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    current_role: str | None = None
    current_lines: list[str] = []
    saw_role = False

    def flush() -> None:
        if current_role in {"user", "assistant"} and current_lines:
            turns.append((current_role, "\n".join(current_lines).strip()))

    for line in transcript.splitlines():
        match = ROLE_LINE_RE.match(line)
        if match:
            flush()
            saw_role = True
            current_role = match.group(1).lower()
            current_lines = [match.group(2).strip()]
            continue
        if current_role is not None:
            current_lines.append(line.strip())
    flush()

    if not saw_role and transcript.strip():
        return [("user", transcript.strip())]
    return [(role, content) for role, content in turns if content]


def _latest_user_requests_no_memories(turns: list[tuple[str, str]]) -> bool:
    for role, content in reversed(turns):
        if role != "user":
            continue
        lowered = content.lower()
        return any(phrase in lowered for phrase in NO_MEMORY_REQUEST_PHRASES)
    return False


def _is_negative_memory(content: str) -> bool:
    lowered = content.lower()
    return any(phrase in lowered for phrase in NEGATIVE_MEMORY_PHRASES)


def _is_temporary_memory(content: str) -> bool:
    lowered = content.lower()
    return any(phrase in lowered for phrase in TEMPORARY_MEMORY_PHRASES)


def _sourced_only_from_assistant(content: str, user_text: str, assistant_text: str) -> bool:
    if not assistant_text.strip():
        return False

    content_lower = content.lower()
    user_lower = user_text.lower()
    assistant_lower = assistant_text.lower()
    if content_lower in assistant_lower and content_lower not in user_lower:
        return True

    content_tokens = _salient_tokens(content)
    user_hits = content_tokens & _salient_tokens(user_text)
    assistant_hits = content_tokens & _salient_tokens(assistant_text)
    return bool(assistant_hits) and len(assistant_hits) >= max(2, len(user_hits) + 2)


def _negated_subjects(turns: list[tuple[str, str]]) -> list[set[str]]:
    subjects: list[set[str]] = []
    for role, content in turns:
        if role != "user":
            continue
        lowered = content.lower()
        for intro in NEGATED_SUBJECT_INTROS:
            start = lowered.find(intro)
            if start < 0:
                continue
            segment = lowered[start + len(intro) :]
            segment = re.split(r"[.;\n]", segment, maxsplit=1)[0]
            terms = _salient_tokens(segment)
            if "codex" in segment or "branch prefix" in segment:
                terms.update({"codex", "branch", "prefix"})
            terms.difference_update({"anything", "everything", "project", "fact", "facts", "memory", "memories"})
            if terms:
                subjects.append(terms)
    return subjects


def _matches_negated_subject(content: str, subjects: list[set[str]]) -> bool:
    content_tokens = _salient_tokens(content)
    content_lower = content.lower()
    for subject in subjects:
        if "codex" in subject and ("codex" in content_lower or "branch prefix" in content_lower):
            return True
        overlap = subject & content_tokens
        required_overlap = 1 if len(subject) == 1 else 2
        if len(overlap) >= required_overlap:
            return True
    return False


def _salient_tokens(text: str) -> set[str]:
    tokens = {token.strip("./") for token in re.findall(r"[a-z0-9][a-z0-9_+./-]{2,}", text.lower())}
    return {token for token in tokens if token and token not in STOPWORDS}


def _ordered_salient_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-z0-9][a-z0-9_+./-]{2,}", text.lower()):
        cleaned = token.strip("./").replace("-", "_")
        if not cleaned or cleaned in STOPWORDS or cleaned in seen:
            continue
        seen.add(cleaned)
        tokens.append(cleaned)
    return tokens


def _topic_from_content(content: str) -> str:
    lowered = content.lower()
    if "concise" in lowered or "answer" in lowered or "communication" in lowered:
        return "communication_style"
    if "nix" in lowered or "flake" in lowered:
        return "development_workflow"
    if "homebrew" in lowered:
        return "homebrew"
    tokens = _ordered_salient_tokens(content)
    return "_".join(tokens[:3]) if tokens else "preference"


def _entity_name_from_content(content: str) -> str:
    lowered = content.lower()
    for preferred in ("miniviking", "openviking", "homebrew", "gemma", "mlx"):
        if preferred in lowered:
            return preferred
    path_match = re.search(r"/[A-Za-z0-9_+./-]+", content)
    if path_match:
        path_parts = [part for part in path_match.group(0).split("/") if part]
        if path_parts:
            return re.sub(r"[^a-z0-9_]+", "_", path_parts[-1].lower()).strip("_") or "project"
    tokens = _ordered_salient_tokens(content)
    return "_".join(tokens[:3]) if tokens else "project"
