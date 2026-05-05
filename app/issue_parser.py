import json
import os
from typing import Any

from openai import OpenAI

client = OpenAI()

ALLOWED_LABELS = {
    "bug",
    "enhancement",
    "documentation",
    "question",
    "high-priority",
    "voice-created",
}


class IssueParserError(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).replace("JSON\n", "", 1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _normalize_labels(labels: Any) -> list[str]:
    if not isinstance(labels, list):
        labels = ["bug"]

    normalized = []
    for label in labels:
        if not isinstance(label, str):
            continue
        value = label.strip().lower()
        if value in ALLOWED_LABELS:
            normalized.append(value)

    normalized.append("voice-created")

    if not any(label in normalized for label in ["bug", "enhancement", "documentation", "question"]):
        normalized.append("bug")

    return sorted(set(normalized))


def parse_transcript_to_issue(transcript: str, source_language: str) -> dict[str, Any]:
    text_model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini")

    if not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "replace_me":
        raise IssueParserError("Missing or invalid OPENAI_API_KEY.")

    language_name = "Hebrew" if source_language == "he" else "English"

    prompt = f"""
You convert a spoken developer request into a clean GitHub issue.

The spoken request language is: {language_name}

Return only valid JSON with this exact schema:
{{
  "title": "short English issue title",
  "body": "professional English issue body",
  "labels": ["bug"]
}}

Rules:
- Always write the issue title and body in English.
- Do not invent technical details that were not mentioned.
- If it is a bug, include label "bug".
- If it is a feature request, include label "enhancement".
- If it is documentation-related, include label "documentation".
- If the request is unclear or asks a question, include label "question".
- If urgent, production, blocked, critical, or high priority is mentioned, include label "high-priority".
- Keep the title short and specific.
- Keep the body practical and useful for an engineer.
- Do not include markdown code fences.

Transcript:
{transcript}
""".strip()

    response = client.responses.create(
        model=text_model,
        input=prompt,
    )

    raw_text = response.output_text.strip()

    try:
        issue = _extract_json(raw_text)
    except Exception:
        issue = {
            "title": "Voice-created issue",
            "body": raw_text or transcript,
            "labels": ["bug"],
        }

    title = str(issue.get("title") or "Voice-created issue").strip()
    body = str(issue.get("body") or transcript).strip()
    labels = _normalize_labels(issue.get("labels"))

    return {
        "title": title[:180],
        "body": body,
        "labels": labels,
    }
