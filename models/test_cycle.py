from __future__ import annotations
from pydantic import BaseModel
from enum import Enum


class ExecutionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    NOT_EXECUTED = "not_executed"


class TestCaseExecution(BaseModel):
    test_case_index: int
    execution_notes: str


class CreateTestCycleRequest(BaseModel):
    cycle_name: str
    jira_ticket_key: str
    test_cases: list[dict]  # list of test case objects from generation step


class ExecuteTestCaseRequest(BaseModel):
    cycle_name: str
    jira_ticket_key: str
    test_case_index: int
    test_case: dict
    execution_notes: str


class ExecuteTestCaseResponse(BaseModel):
    test_case_title: str
    status: ExecutionStatus
    bug_key: str | None = None
    bug_url: str | None = None


class TestCycleStatus(BaseModel):
    cycle_name: str
    jira_ticket_key: str
    total: int
    passed: int
    failed: int
    not_executed: int
    failed_cases: list[dict]
