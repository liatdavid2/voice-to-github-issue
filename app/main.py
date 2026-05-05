import os
import tempfile
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI

from github_client import GitHubApiError, GitHubConfigError, create_github_issue
from issue_parser import IssueParserError, parse_transcript_to_issue
from team_config import TEAM_MEMBERS

load_dotenv()

app = FastAPI(title="Voice to GitHub Issue")
client = OpenAI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "github_owner": os.getenv("GITHUB_OWNER", ""),
        "github_repo": os.getenv("GITHUB_REPO", ""),
        "target_repo_url": _build_repo_url(),
    }


@app.get("/api/team-members")
def get_team_members() -> list[dict[str, str]]:
    return TEAM_MEMBERS


@app.post("/api/preview-issue")
async def preview_issue(
    audio: UploadFile = File(...),
    language: str = Form(...),
    assignee: str = Form(""),
) -> dict[str, Any]:
    if language not in {"he", "en"}:
        raise HTTPException(status_code=400, detail="Language must be 'he' or 'en'.")

    transcript = await transcribe_audio(audio=audio, language=language)

    try:
        issue = parse_transcript_to_issue(transcript=transcript, source_language=language)
    except IssueParserError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Issue parsing failed: {exc}") from exc

    issue["assignees"] = [assignee] if assignee else []

    return {
        "transcript": transcript,
        "issue": issue,
        "target_repo_url": _build_repo_url(),
    }


@app.post("/api/create-issue")
async def create_issue(
    title: str = Form(...),
    body: str = Form(...),
    labels: str = Form("voice-created, bug"),
    assignee: str = Form(""),
) -> dict[str, Any]:
    label_list = _parse_labels(labels)
    if "voice-created" not in label_list:
        label_list.append("voice-created")

    assignees = [assignee] if assignee else []

    try:
        created = create_github_issue(
            title=title,
            body=body,
            labels=label_list,
            assignees=assignees,
        )
    except (GitHubConfigError, GitHubApiError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected GitHub error: {exc}") from exc

    return {
        "created": True,
        "url": created.get("html_url"),
        "number": created.get("number"),
        "title": created.get("title"),
        "labels": [label.get("name") for label in created.get("labels", [])],
        "assignees": [user.get("login") for user in created.get("assignees", [])],
    }


async def transcribe_audio(audio: UploadFile, language: str) -> str:
    if not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "replace_me":
        raise HTTPException(status_code=500, detail="Missing or invalid OPENAI_API_KEY.")

    suffix = os.path.splitext(audio.filename or "recording.webm")[1] or ".webm"
    content = await audio.read()

    if not content:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        model_name = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

        with open(temp_path, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                model=model_name,
                file=audio_file,
                language=language,
            )

        transcript = getattr(result, "text", "") or ""
        transcript = transcript.strip()

        if not transcript:
            raise HTTPException(status_code=500, detail="Transcription returned empty text.")

        return transcript

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _parse_labels(labels: str) -> list[str]:
    return sorted(set(label.strip() for label in labels.split(",") if label.strip()))


def _build_repo_url() -> str:
    owner = os.getenv("GITHUB_OWNER", "").strip()
    repo = os.getenv("GITHUB_REPO", "").strip()

    if not owner or not repo:
        return ""

    return f"https://github.com/{owner}/{repo}"
