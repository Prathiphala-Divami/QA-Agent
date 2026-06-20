from __future__ import annotations
import base64
import httpx
from config import settings

BASE = settings.jira_base_url.rstrip("/")
API = f"{BASE}/rest/api/3"

# Jira Cloud uses Basic auth: base64(email:api_token)
_token = base64.b64encode(
    f"{settings.jira_email}:{settings.jira_api_token}".encode()
).decode()

HEADERS = {
    "Authorization": f"Basic {_token}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def _client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=30)


def _client_for(issue_key: str) -> tuple[httpx.Client, str]:
    """Return (client, api_base) for the correct Jira instance based on issue key prefix."""
    project = issue_key.split("-")[0].upper()

    # Projects that live on the second Jira instance
    jira2_projects = {"SCRUM"}  # add more project keys here as needed

    if project in jira2_projects and settings.jira2_email and settings.jira2_api_token:
        token2 = base64.b64encode(
            f"{settings.jira2_email}:{settings.jira2_api_token}".encode()
        ).decode()
        headers2 = {
            "Authorization": f"Basic {token2}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        base2 = settings.jira2_base_url.rstrip("/")
        return httpx.Client(headers=headers2, timeout=30), f"{base2}/rest/api/3"

    return httpx.Client(headers=HEADERS, timeout=30), API


QALITY_TEST_ISSUE_TYPE_ID = "10315"  # "QAlity Test" issue type in IIRM project


def _adf_text(text: str) -> dict:
    """Single plain-text paragraph in ADF."""
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _adf_heading(text: str, level: int = 3) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": [{"type": "text", "text": text}]}


def _adf_bullet(items: list[str]) -> dict:
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": item}]}]}
            for item in items
        ]
    }


def _adf_ordered(items: list[str]) -> dict:
    return {
        "type": "orderedList",
        "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": item}]}]}
            for item in items
        ]
    }


def _build_test_case_adf(tc: dict) -> dict:
    """Build rich ADF description for a QAlity Test issue from a test case dict."""
    content = []

    if tc.get("objective"):
        content.append(_adf_heading("Objective"))
        content.append(_adf_text(tc["objective"]))

    if tc.get("preconditions"):
        content.append(_adf_heading("Preconditions"))
        content.append(_adf_bullet(tc["preconditions"]))

    if tc.get("steps"):
        content.append(_adf_heading("Test Steps"))
        content.append(_adf_ordered(tc["steps"]))

    if tc.get("expected_result"):
        content.append(_adf_heading("Expected Result"))
        content.append(_adf_text(tc["expected_result"]))

    return {"type": "doc", "version": 1, "content": content}


# ── Connection ─────────────────────────────────────────────────────────────────

def test_connection() -> dict:
    """Verify credentials and return project info."""
    with _client() as c:
        # Check current user
        me = c.get(f"{API}/myself")
        me.raise_for_status()
        user = me.json()

        # Check project
        proj = c.get(f"{API}/project/{settings.jira_project_key}")
        proj.raise_for_status()
        project = proj.json()

        return {
            "connected": True,
            "user": user.get("displayName"),
            "email": user.get("emailAddress"),
            "project_key": project.get("key"),
            "project_name": project.get("name"),
            "project_type": project.get("projectTypeKey"),
        }


# ── Issues ─────────────────────────────────────────────────────────────────────

def create_issue(payload: dict) -> dict:
    with _client() as c:
        r = c.post(f"{API}/issue", json=payload)
        r.raise_for_status()
        return r.json()


def get_issue(issue_key: str) -> dict:
    client, api = _client_for(issue_key)
    with client as c:
        r = c.get(f"{api}/issue/{issue_key}")
        r.raise_for_status()
        return r.json()


def update_issue(issue_key: str, payload: dict) -> None:
    with _client() as c:
        r = c.put(f"{API}/issue/{issue_key}", json=payload)
        r.raise_for_status()


def link_issues(inward_key: str, outward_key: str, link_type: str = "Relates") -> None:
    payload = {
        "type": {"name": link_type},
        "inwardIssue": {"key": inward_key},
        "outwardIssue": {"key": outward_key},
    }
    with _client() as c:
        r = c.post(f"{API}/issueLink", json=payload)
        r.raise_for_status()


def search_issues(jql: str, fields: list[str] | None = None, max_results: int = 100) -> list[dict]:
    body: dict = {"jql": jql, "maxResults": max_results}
    if fields:
        body["fields"] = fields
    with _client() as c:
        r = c.post(f"{API}/search/jql", json=body)
        r.raise_for_status()
        return r.json().get("issues", [])


# ── Project ────────────────────────────────────────────────────────────────────

def get_project(project_key: str) -> dict:
    with _client() as c:
        r = c.get(f"{API}/project/{project_key}")
        r.raise_for_status()
        return r.json()


def get_project_issue_types(project_key: str) -> list[dict]:
    with _client() as c:
        r = c.get(f"{API}/issue/createmeta", params={"projectKeys": project_key})
        r.raise_for_status()
        projects = r.json().get("projects", [])
        return projects[0].get("issuetypes", []) if projects else []


def get_custom_fields() -> list[dict]:
    """List all fields including custom ones — useful for finding Quality Plus field IDs."""
    with _client() as c:
        r = c.get(f"{API}/field")
        r.raise_for_status()
        return r.json()


# ── Users ──────────────────────────────────────────────────────────────────────

def search_users(query: str) -> list[dict]:
    with _client() as c:
        r = c.get(f"{API}/user/search", params={"query": query, "maxResults": 10})
        r.raise_for_status()
        return r.json()


def get_user(query: str) -> dict | None:
    results = search_users(query)
    return results[0] if results else None


# ── Test Cases (QAlity Test) ───────────────────────────────────────────────────

def fetch_story_text(story_key: str) -> str:
    """Fetch story summary + description as plain text for AI input."""
    issue = get_issue(story_key)
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")

    # Description in ADF — extract plain text from it
    desc_adf = fields.get("description") or {}
    desc_text = _extract_text_from_adf(desc_adf)

    return f"Story: {story_key}\nSummary: {summary}\n\nDescription:\n{desc_text}".strip()


def _extract_text_from_adf(node: dict) -> str:
    """Recursively extract plain text from an ADF document."""
    if not node:
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts = [_extract_text_from_adf(child) for child in node.get("content", [])]
    return "\n".join(p for p in parts if p)


def _get_project_key_from_issue(story_key: str) -> str:
    """Extract project key from issue key e.g. QI-19 → QI."""
    return story_key.split("-")[0]


def _has_qality_test(project_key: str) -> bool:
    """Check if the project has the QAlity Test issue type."""
    with _client() as c:
        r = c.get(f"{API}/issue/createmeta", params={"projectKeys": project_key, "expand": "projects.issuetypes"})
        r.raise_for_status()
        projects = r.json().get("projects", [])
        if not projects:
            return False
        names = [it["name"] for it in projects[0].get("issuetypes", [])]
        return "QAlity Test" in names


def create_test_case(story_key: str, tc: dict) -> dict:
    """Create a test case issue in Jira linked to the given story.
    Uses QAlity Test if available, otherwise falls back to Sub-task."""
    project_key = _get_project_key_from_issue(story_key)
    priority_map = {"High": "High", "Medium": "Medium", "Low": "Low"}

    if _has_qality_test(project_key):
        issuetype: dict = {"id": QALITY_TEST_ISSUE_TYPE_ID}
    else:
        issuetype = {"name": "Sub-task"}

    payload = {
        "fields": {
            "project": {"key": project_key},
            "issuetype": issuetype,
            "summary": f"[TC] {tc['title']}",
            "description": _build_test_case_adf(tc),
            "priority": {"name": priority_map.get(tc.get("priority", "Medium"), "Medium")},
            "labels": [tc.get("test_type", "Positive").replace(" ", "-").lower()],
            "parent": {"key": story_key},
        }
    }
    with _client() as c:
        r = c.post(f"{API}/issue", json=payload)
        r.raise_for_status()
        return r.json()


# ── Attachments ────────────────────────────────────────────────────────────────

def upload_attachment(issue_key: str, file_bytes: bytes, filename: str) -> list[dict]:
    headers = {
        "Authorization": f"Basic {_token}",
        "X-Atlassian-Token": "no-check",
    }
    with httpx.Client(headers=headers, timeout=60) as c:
        r = c.post(
            f"{API}/issue/{issue_key}/attachments",
            files={"file": (filename, file_bytes)},
        )
        r.raise_for_status()
        return r.json()
