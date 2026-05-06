from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from issue_parser import parse_transcript_to_issue
from github_client import create_github_issue


class IssueState(TypedDict, total=False):
    transcript: str
    source_language: str
    issue: dict[str, Any]
    title: str
    body: str
    labels: list[str]
    assignees: list[str]
    created_issue: dict[str, Any]


def voice_transcript_agent(state: IssueState) -> IssueState:
    # In the current project, transcription is already done in main.py.
    # This agent represents the transcript as a graph step.
    return state


def issue_draft_agent(state: IssueState) -> IssueState:
    issue = parse_transcript_to_issue(
        transcript=state["transcript"],
        source_language=state["source_language"],
    )
    return {
        **state,
        "issue": issue,
    }


def issue_validation_agent(state: IssueState) -> IssueState:
    issue = state["issue"]

    title = str(issue.get("title") or "Voice-created issue").strip()
    body = str(issue.get("body") or state["transcript"]).strip()
    labels = list(issue.get("labels") or [])

    if "voice-created" not in labels:
        labels.append("voice-created")

    return {
        **state,
        "issue": {
            **issue,
            "title": title[:180],
            "body": body,
            "labels": sorted(set(labels)),
        },
    }


def github_issue_api_agent(state: IssueState) -> IssueState:
    created = create_github_issue(
        title=state["title"],
        body=state["body"],
        labels=state["labels"],
        assignees=state["assignees"],
    )
    return {
        **state,
        "created_issue": created,
    }


def build_preview_graph():
    graph = StateGraph(IssueState)

    graph.add_node("voice_transcript_agent", voice_transcript_agent)
    graph.add_node("issue_draft_agent", issue_draft_agent)
    graph.add_node("issue_validation_agent", issue_validation_agent)

    graph.set_entry_point("voice_transcript_agent")
    graph.add_edge("voice_transcript_agent", "issue_draft_agent")
    graph.add_edge("issue_draft_agent", "issue_validation_agent")
    graph.add_edge("issue_validation_agent", END)

    return graph.compile()


def build_create_graph():
    graph = StateGraph(IssueState)

    graph.add_node("github_issue_api_agent", github_issue_api_agent)

    graph.set_entry_point("github_issue_api_agent")
    graph.add_edge("github_issue_api_agent", END)

    return graph.compile()


preview_graph = build_preview_graph()
create_graph = build_create_graph()


def run_preview_graph(transcript: str, source_language: str) -> dict[str, Any]:
    result = preview_graph.invoke(
        {
            "transcript": transcript,
            "source_language": source_language,
        }
    )
    return result["issue"]


def run_create_graph(
    title: str,
    body: str,
    labels: list[str],
    assignees: list[str],
) -> dict[str, Any]:
    result = create_graph.invoke(
        {
            "title": title,
            "body": body,
            "labels": labels,
            "assignees": assignees,
        }
    )
    return result["created_issue"]