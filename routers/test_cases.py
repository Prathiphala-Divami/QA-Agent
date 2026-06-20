from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ai_service import generate_test_cases
import jira_client as jira
from config import settings

router = APIRouter(prefix="/test-cases", tags=["Test Case Generation"])


class GenerateAndLogRequest(BaseModel):
    story_key: str
    extra_spec: str | None = None  # optional additional spec beyond what's in Jira


class LoggedTestCase(BaseModel):
    jira_key: str
    jira_url: str
    title: str
    test_type: str
    priority: str


class GenerateAndLogResponse(BaseModel):
    story_key: str
    story_summary: str
    total_generated: int
    logged: list[LoggedTestCase]
    failed: list[str]


@router.post("/generate-and-log", response_model=GenerateAndLogResponse)
def generate_and_log(request: GenerateAndLogRequest):
    # Step 1: Fetch story from Jira
    try:
        story_text = jira.fetch_story_text(request.story_key)
        story_issue = jira.get_issue(request.story_key)
        story_summary = story_issue["fields"].get("summary", "")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not fetch story {request.story_key}: {str(e)}")

    # Append extra spec if provided
    if request.extra_spec:
        story_text += f"\n\nAdditional Specification:\n{request.extra_spec}"

    # Step 2: Generate test cases via Claude AI
    try:
        raw_cases = generate_test_cases(story_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

    # Step 3: Log each test case as QAlity Test in Jira under the story
    logged = []
    failed = []

    for tc in raw_cases:
        try:
            result = jira.create_test_case(request.story_key, tc)
            issue_key = result["key"]
            logged.append(LoggedTestCase(
                jira_key=issue_key,
                jira_url=f"{settings.jira_base_url}/browse/{issue_key}",
                title=tc["title"],
                test_type=tc.get("test_type", "Positive"),
                priority=tc.get("priority", "Medium"),
            ))
        except Exception as e:
            failed.append(f"{tc.get('title', 'Unknown')}: {str(e)}")

    return GenerateAndLogResponse(
        story_key=request.story_key,
        story_summary=story_summary,
        total_generated=len(raw_cases),
        logged=logged,
        failed=failed,
    )
