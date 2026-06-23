from __future__ import annotations
import json
from groq import Groq
from config import settings

_client = Groq(api_key=settings.groq_api_key)
MODEL = "llama-3.3-70b-versatile"


def _ask(system: str, user: str) -> str:
    msg = _client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return msg.choices[0].message.content


def _ask_json(system: str, user: str) -> dict | list:
    raw = _ask(system, user + "\n\nRespond with valid JSON only. No markdown, no explanation.")
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


# ── Intent Detection ──────────────────────────────────────────────────────────

INTENT_SYSTEM = """
You are an intent router for a QA CLI tool.
Parse the user's natural language prompt and return JSON:
{
  "intent": "test-cases | bug | test-cycle",
  "story_key": "e.g. IIRM-9566 or SCRUM-5, or null",
  "cycle_name": "e.g. Build 1 — only for test-cycle intent, or null",
  "spec_file": "path/to/file.txt if mentioned, or null",
  "use_jira_only": true or false
}

Rules:
- "test-cases": user wants to generate or create test cases
- "bug": user wants to log, report, or create a bug
- "test-cycle": user wants to start, run, or manage a test cycle or build
If no cycle name mentioned, default to "Build 1".
If no spec file and not told to use Jira description only, set use_jira_only to true.
"""


def detect_intent(prompt: str) -> dict:
    return _ask_json(INTENT_SYSTEM, f"User prompt: {prompt}")


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
    return result


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
