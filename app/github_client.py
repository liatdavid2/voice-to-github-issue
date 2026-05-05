import os
from typing import Any

import requests


class GitHubConfigError(RuntimeError):
    pass


class GitHubApiError(RuntimeError):
    pass


LABEL_COLORS = {
    "bug": "d73a4a",
    "enhancement": "a2eeef",
    "documentation": "0075ca",
    "question": "d876e3",
    "high-priority": "b60205",
    "voice-created": "5319e7",
}


def _get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value == "replace_me":
        raise GitHubConfigError(f"Missing or invalid environment variable: {name}")
    return value


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _ensure_labels_exist(owner: str, repo: str, token: str, labels: list[str]) -> None:
    for label in labels:
        color = LABEL_COLORS.get(label, "ededed")
        url = f"https://api.github.com/repos/{owner}/{repo}/labels"
        payload = {
            "name": label,
            "color": color,
            "description": "Created by the Voice to GitHub Issue demo tool.",
        }

        response = requests.post(url, json=payload, headers=_headers(token), timeout=30)

        # 201 means created. 422 usually means the label already exists.
        # If the token cannot create labels, issue creation may still succeed if labels already exist.
        if response.status_code in {201, 422, 403, 404}:
            continue


def create_github_issue(title: str, body: str, labels: list[str], assignees: list[str]) -> dict[str, Any]:
    owner = _get_required_env("GITHUB_OWNER")
    repo = _get_required_env("GITHUB_REPO")
    token = _get_required_env("GITHUB_TOKEN")

    url = f"https://api.github.com/repos/{owner}/{repo}/issues"

    clean_labels = sorted(set(label.strip() for label in labels if label.strip()))
    clean_assignees = sorted(set(assignee.strip() for assignee in assignees if assignee.strip()))

    if clean_labels:
        _ensure_labels_exist(owner=owner, repo=repo, token=token, labels=clean_labels)

    payload = {
        "title": title.strip(),
        "body": body.strip(),
        "labels": clean_labels,
        "assignees": clean_assignees,
    }

    response = requests.post(url, json=payload, headers=_headers(token), timeout=30)

    if response.status_code == 201:
        return response.json()

    # A common demo failure is an invalid assignee or missing label permission.
    # Retry once without assignees and labels so the issue itself is still created.
    if response.status_code == 422 and (clean_assignees or clean_labels):
        fallback_body = body.strip() + "\n\n---\nNote: Labels or assignees could not be applied automatically."
        fallback_payload = {
            "title": title.strip(),
            "body": fallback_body,
        }
        fallback_response = requests.post(url, json=fallback_payload, headers=_headers(token), timeout=30)
        if fallback_response.status_code == 201:
            return fallback_response.json()

    raise GitHubApiError(f"GitHub issue creation failed: {response.status_code} {response.text}")
