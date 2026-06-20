from __future__ import annotations
import json
import anthropic
from config import settings

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
MODEL = "claude-sonnet-4-6"


def _ask(system: str, user: str) -> str:
    msg = _client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


def _ask_json(system: str, user: str) -> dict | list:
    raw = _ask(system, user + "\n\nRespond with valid JSON only. No markdown, no explanation.")
    # Strip markdown fences if model adds them
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


# ── Bug Logging ────────────────────────────────────────────────────────────────

BUG_SYSTEM = """
You are a senior QA engineer. Given a description of a bug, extract and structure it into a Jira bug report.
Return a JSON object with these exact keys:
{
  "summary": "concise one-line bug title",
  "description": "detailed description with context",
  "steps_to_reproduce": ["step 1", "step 2", "..."],
  "expected_result": "what should happen",
  "actual_result": "what actually happens",
  "severity": "Critical | High | Medium | Low",
  "priority": "Highest | High | Medium | Low | Lowest",
  "environment": "browser/OS/version if mentioned, else 'Not specified'",
  "suggested_category": "Functional | UI/UX | Performance | Security | Data | Integration | Usability | Accessibility | Other"
}

For suggested_category, pick the one that best fits the bug based on its description.
"""


def parse_bug(raw_description: str) -> dict:
    return _ask_json(BUG_SYSTEM, f"Bug description:\n{raw_description}")


# ── Test Case Generation ───────────────────────────────────────────────────────

TEST_CASE_SYSTEM = """
You are a senior QA engineer specializing in test case design.
Given a feature description or Jira ticket, generate comprehensive test cases covering:
1. Positive/happy-path scenarios
2. Negative scenarios
3. Edge cases
4. Implicit functionality (things not explicitly stated but logically required)
5. UI/UX validations where applicable

Return a JSON array of test case objects, each with:
{
  "title": "Test case title",
  "objective": "What this test verifies",
  "preconditions": ["precondition 1", "precondition 2"],
  "steps": ["step 1", "step 2", "..."],
  "expected_result": "expected outcome",
  "test_type": "Positive | Negative | Edge Case | Implicit",
  "priority": "High | Medium | Low"
}

Generate at minimum 8-12 test cases. Be thorough and think about what a user could do wrong.
"""


def generate_test_cases(feature_description: str) -> list[dict]:
    result = _ask_json(TEST_CASE_SYSTEM, f"Feature/ticket description:\n{feature_description}")
    if isinstance(result, dict) and "test_cases" in result:
        return result["test_cases"]
    return result  # already a list


# ── Test Execution Analysis ────────────────────────────────────────────────────

EXECUTION_SYSTEM = """
You are a QA engineer analyzing test execution results.
Given a test case and its actual execution outcome, determine:
- Whether it passed or failed
- If failed: extract a structured bug report

Return JSON:
{
  "status": "passed | failed",
  "bug": null | {
    "summary": "...",
    "description": "...",
    "steps_to_reproduce": ["..."],
    "expected_result": "...",
    "actual_result": "...",
    "severity": "Critical | High | Medium | Low",
    "priority": "Highest | High | Medium | Low | Lowest"
  }
}
"""


def analyze_execution(test_case: dict, execution_notes: str) -> dict:
    prompt = f"""
Test Case:
Title: {test_case.get('title')}
Steps: {json.dumps(test_case.get('steps', []))}
Expected Result: {test_case.get('expected_result')}

Execution Notes / Actual Outcome:
{execution_notes}
"""
    return _ask_json(EXECUTION_SYSTEM, prompt)
