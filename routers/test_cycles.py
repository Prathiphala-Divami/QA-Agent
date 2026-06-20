from __future__ import annotations
"""
Test Cycle management.

Since Quality Plus API details are pending, this module manages test cycles
using in-memory state (a simple dict keyed by cycle_name).
Once you share the Quality Plus API, we replace the in-memory store
with real API calls — all business logic stays the same.
"""
from fastapi import APIRouter, HTTPException
from models.test_cycle import (
    CreateTestCycleRequest,
    ExecuteTestCaseRequest,
    ExecuteTestCaseResponse,
    ExecutionStatus,
    TestCycleStatus,
)
from ai_service import analyze_execution, parse_bug
import jira_client as jira
from config import settings

router = APIRouter(prefix="/test-cycles", tags=["Test Cycle Management"])

# In-memory store: cycle_name → { ticket_key, test_cases: [{...meta, status, bug_key}] }
_cycles: dict[str, dict] = {}


@router.post("/create")
def create_test_cycle(request: CreateTestCycleRequest):
    if request.cycle_name in _cycles:
        raise HTTPException(status_code=409, detail=f"Cycle '{request.cycle_name}' already exists")

    enriched = [
        {**tc, "status": ExecutionStatus.NOT_EXECUTED, "bug_key": None}
        for tc in request.test_cases
    ]

    _cycles[request.cycle_name] = {
        "jira_ticket_key": request.jira_ticket_key,
        "test_cases": enriched,
    }

    return {
        "message": f"Test cycle '{request.cycle_name}' created",
        "ticket": request.jira_ticket_key,
        "total_test_cases": len(enriched),
    }


@router.post("/execute", response_model=ExecuteTestCaseResponse)
def execute_test_case(request: ExecuteTestCaseRequest):
    cycle = _cycles.get(request.cycle_name)
    if not cycle:
        raise HTTPException(status_code=404, detail=f"Cycle '{request.cycle_name}' not found")

    test_cases = cycle["test_cases"]
    idx = request.test_case_index
    if idx < 0 or idx >= len(test_cases):
        raise HTTPException(status_code=400, detail=f"Test case index {idx} out of range")

    tc = test_cases[idx]

    # AI determines pass/fail and extracts bug if failed
    try:
        analysis = analyze_execution(request.test_case, request.execution_notes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")

    status = ExecutionStatus(analysis["status"])
    tc["status"] = status

    bug_key = None
    bug_url = None

    if status == ExecutionStatus.FAILED and analysis.get("bug"):
        bug_data = analysis["bug"]
        description = f"""
*Description:*
{bug_data['description']}

*Steps to Reproduce:*
{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(bug_data['steps_to_reproduce']))}

*Expected Result:*
{bug_data['expected_result']}

*Actual Result:*
{bug_data['actual_result']}

*Linked Test Case:* {tc.get('title', '')}
*Test Cycle:* {request.cycle_name}
""".strip()

        payload = {
            "fields": {
                "project": {"key": settings.jira_project_key},
                "issuetype": {"name": "Bug"},
                "summary": bug_data["summary"],
                "description": description,
                "priority": {"name": bug_data.get("priority", "Medium")},
                "labels": [
                    f"severity-{bug_data.get('severity', 'medium').lower()}",
                    f"cycle-{request.cycle_name.lower().replace(' ', '-')}",
                ],
            }
        }

        try:
            result = jira.create_issue(payload)
            bug_key = result["key"]
            bug_url = f"{settings.jira_base_url}/browse/{bug_key}"
            tc["bug_key"] = bug_key

            # Link bug to the parent ticket
            try:
                jira.link_issues(bug_key, cycle["jira_ticket_key"], "Relates")
            except Exception:
                pass
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Jira bug creation failed: {str(e)}")

    return ExecuteTestCaseResponse(
        test_case_title=tc.get("title", f"Test Case #{idx}"),
        status=status,
        bug_key=bug_key,
        bug_url=bug_url,
    )


@router.get("/status/{cycle_name}", response_model=TestCycleStatus)
def get_cycle_status(cycle_name: str):
    cycle = _cycles.get(cycle_name)
    if not cycle:
        raise HTTPException(status_code=404, detail=f"Cycle '{cycle_name}' not found")

    tcs = cycle["test_cases"]
    passed = sum(1 for tc in tcs if tc["status"] == ExecutionStatus.PASSED)
    failed = sum(1 for tc in tcs if tc["status"] == ExecutionStatus.FAILED)
    not_executed = sum(1 for tc in tcs if tc["status"] == ExecutionStatus.NOT_EXECUTED)
    failed_cases = [tc for tc in tcs if tc["status"] == ExecutionStatus.FAILED]

    return TestCycleStatus(
        cycle_name=cycle_name,
        jira_ticket_key=cycle["jira_ticket_key"],
        total=len(tcs),
        passed=passed,
        failed=failed,
        not_executed=not_executed,
        failed_cases=failed_cases,
    )


@router.post("/next-cycle")
def create_next_cycle(current_cycle_name: str, new_cycle_name: str):
    """Create a new cycle with only the failed test cases from the previous cycle."""
    cycle = _cycles.get(current_cycle_name)
    if not cycle:
        raise HTTPException(status_code=404, detail=f"Cycle '{current_cycle_name}' not found")

    if new_cycle_name in _cycles:
        raise HTTPException(status_code=409, detail=f"Cycle '{new_cycle_name}' already exists")

    failed_cases = [
        {**tc, "status": ExecutionStatus.NOT_EXECUTED, "bug_key": None}
        for tc in cycle["test_cases"]
        if tc["status"] == ExecutionStatus.FAILED
    ]

    if not failed_cases:
        return {"message": "No failed test cases. All tests passed in the previous cycle!"}

    _cycles[new_cycle_name] = {
        "jira_ticket_key": cycle["jira_ticket_key"],
        "test_cases": failed_cases,
    }

    return {
        "message": f"Cycle '{new_cycle_name}' created from failed cases of '{current_cycle_name}'",
        "ticket": cycle["jira_ticket_key"],
        "total_test_cases": len(failed_cases),
    }


@router.get("/list")
def list_cycles():
    return [
        {
            "cycle_name": name,
            "ticket": data["jira_ticket_key"],
            "total": len(data["test_cases"]),
            "passed": sum(1 for tc in data["test_cases"] if tc["status"] == ExecutionStatus.PASSED),
            "failed": sum(1 for tc in data["test_cases"] if tc["status"] == ExecutionStatus.FAILED),
        }
        for name, data in _cycles.items()
    ]
