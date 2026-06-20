from __future__ import annotations
from fastapi import APIRouter, HTTPException, Form, File, UploadFile
from typing import Annotated
from models.bug import BugPriority, BugCategory, LogBugResponse
from ai_service import parse_bug
import jira_client as jira
from config import settings

router = APIRouter(prefix="/bugs", tags=["Bug Logging"])

BUG_CATEGORIES = {c.value for c in BugCategory}


@router.post("/log", response_model=LogBugResponse)
async def log_bug(
    raw_description: Annotated[str, Form(description="Plain text description of the bug")],
    story_key: Annotated[str | None, Form(description="Jira story/ticket this bug belongs to (e.g. QA-101)")] = None,
    priority: Annotated[BugPriority | None, Form(description="Bug priority. If not provided, AI will suggest one.")] = None,
    assignee: Annotated[str | None, Form(description="Jira username to assign this bug to")] = None,
    bug_category: Annotated[BugCategory | None, Form(description="Bug category. If not provided, AI will suggest one.")] = None,
    attachment: Annotated[UploadFile | None, File(description="Optional screenshot or file to attach")] = None,
):
    # Step 1: AI parses the free-text description
    parsed = parse_bug(raw_description)

    # Step 2: User-provided values override AI suggestions
    final_priority = priority.value if priority else parsed.get("priority", "Medium")
    final_category = bug_category.value if bug_category else parsed.get("suggested_category", "Functional")

    # Step 3: Validate assignee exists in Jira (if provided)
    assignee_name = None
    if assignee:
        user = jira.get_user(assignee)
        if not user:
            raise HTTPException(status_code=404, detail=f"Jira user '{assignee}' not found")
        assignee_name = user.get("name") or user.get("accountId")

    # Step 4: Build the Jira description body
    description_body = f"""
*Description:*
{parsed['description']}

*Steps to Reproduce:*
{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(parsed['steps_to_reproduce']))}

*Expected Result:*
{parsed['expected_result']}

*Actual Result:*
{parsed['actual_result']}

*Environment:*
{parsed.get('environment', 'Not specified')}

*Bug Category:* {final_category}
""".strip()

    # Step 5: Build Jira issue payload
    payload: dict = {
        "fields": {
            "project": {"key": settings.jira_project_key},
            "issuetype": {"name": "Bug"},
            "summary": parsed["summary"],
            "description": description_body,
            "priority": {"name": final_priority},
            "labels": [
                f"severity-{parsed.get('severity', 'medium').lower()}",
                f"category-{final_category.lower().replace('/', '-').replace(' ', '-')}",
            ],
        }
    }

    if assignee_name:
        payload["fields"]["assignee"] = {"name": assignee_name}

    # Step 6: Create the bug in Jira
    try:
        result = jira.create_issue(payload)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Jira issue creation failed: {str(e)}")

    issue_key = result["key"]

    # Step 7: Link to parent story if provided
    if story_key:
        try:
            jira.link_issues(issue_key, story_key, "Relates")
        except Exception:
            pass  # best-effort linking

    # Step 8: Upload attachment if provided
    attachment_uploaded = False
    if attachment and attachment.filename:
        try:
            file_bytes = await attachment.read()
            jira.upload_attachment(issue_key, file_bytes, attachment.filename)
            attachment_uploaded = True
        except Exception as e:
            # Bug is created — don't fail the whole request over attachment
            pass

    return LogBugResponse(
        jira_key=issue_key,
        jira_url=f"{settings.jira_base_url}/browse/{issue_key}",
        summary=parsed["summary"],
        severity=parsed.get("severity", "Medium"),
        priority=final_priority,
        category=final_category,
        assignee=assignee,
        story_key=story_key,
        attachment_uploaded=attachment_uploaded,
    )
