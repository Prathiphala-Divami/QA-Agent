from __future__ import annotations
from pydantic import BaseModel


class GenerateTestCasesRequest(BaseModel):
    jira_ticket_key: str | None = None   # fetch description from Jira
    feature_description: str | None = None  # or provide description directly


class TestCase(BaseModel):
    title: str
    objective: str
    preconditions: list[str]
    steps: list[str]
    expected_result: str
    test_type: str
    priority: str


class GenerateTestCasesResponse(BaseModel):
    source_ticket: str | None
    test_cases: list[TestCase]
    total: int
