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


    prompt = f"""
You convert a spoken developer request into a clean GitHub issue.

The spoken request language is: {source_language}

Return only valid JSON with this exact schema:
{{
  "title": "short English issue title",
  "body": "direct English translation of the user's spoken request",
  "labels": ["bug" or "enhancement" or "high-priority"],
  "assignee_name": "person name mentioned by the user, or empty string"
}}

Rules:
- Always write the title and body in English.
- The title must be a short summary suitable for a GitHub issue title.
- The title should be 5 to 12 words.
- The body must be a direct English translation of what the user said.
- Do not summarize the body.
- Do not shorten the body.
- Do not rewrite the body into generic issue text.
- Do not add details that the user did not say.
- Do not add generic text like "Please investigate" unless the user said it.
- If the user spoke Hebrew, translate the full meaning into English.
- Keep the user's wording and intent as close as possible.
- Do not invent an assignee.
- If the user says bug, באג, תקלה, problem, error, or not working, include "bug".
- If the user says feature, פיצ'ר, improvement, or add new capability, include "enhancement".
- If the user says urgent, critical, דחוף, קריטי, production, or blocking, include "high-priority".
- If the user says assign to someone, extract the person name into assignee_name.

Examples:

Hebrew transcript:
פתחי באג על זה שכפתור שמירה לא עובד במסך פרופיל ותשייכי לליאת

Output:
{{
  "title": "Save button does not work on profile screen",
  "body": "Open a bug about the save button not working on the profile screen and assign it to Liat.",
  "labels": ["bug"],
  "assignee_name": "ליאת"
}}

Hebrew transcript:
תפתחי פיצ'ר להוסיף סינון לפי תאריך במסך משימות

Output:
{{
  "title": "Add date filter to tasks screen",
  "body": "Open a feature to add filtering by date on the tasks screen.",
  "labels": ["enhancement"],
  "assignee_name": ""
}}

Transcript:
{transcript}
"""

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
