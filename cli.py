from __future__ import annotations
import sys
import os
import argparse

# Make sure the project root is in path
sys.path.insert(0, os.path.dirname(__file__))

import jira_client as jira
from ai_service import generate_test_cases, parse_bug


# ── Helpers ────────────────────────────────────────────────────────────────────

def _separator():
    print("\n" + "─" * 60)


def _read_multiline(prompt: str) -> str:
    """Read multi-line input until user types END on a new line."""
    print(prompt)
    print("(Type your text. When done, type END on a new line and press Enter)\n")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_generate_test_cases(story_key: str, spec_file: str | None, jira_only: bool = False):
    _separator()
    print(f"  GENERATE & LOG TEST CASES → {story_key}")
    _separator()

    # Step 1: Fetch story from Jira
    print(f"\n[1/4] Fetching story {story_key} from Jira...")
    try:
        story_text = jira.fetch_story_text(story_key)
        issue = jira.get_issue(story_key)
        story_summary = issue["fields"].get("summary", "")
        print(f"      ✓ Story   : {story_summary}")
    except Exception as e:
        print(f"      ✗ Failed to fetch story: {e}")
        return

    # Step 2: Resolve spec source
    print("\n[2/4] Reading spec...")
    if jira_only:
        full_input = story_text
        print(f"      ✓ Using Jira description only")
    elif spec_file:
        try:
            with open(spec_file) as f:
                extra_spec = f.read().strip()
            print(f"      ✓ Loaded spec from file: {spec_file}")
            full_input = f"{story_text}\n\nProduct Specification:\n{extra_spec}"
        except Exception as e:
            print(f"      ✗ Could not read file: {e}")
            return
    else:
        extra_spec = _read_multiline("\n      Paste your product spec below (or press Enter + END to use Jira description only):")
        full_input = f"{story_text}\n\nAdditional Specification:\n{extra_spec}" if extra_spec else story_text

    # Step 3: Generate test cases via AI
    print("\n[3/4] Generating test cases with Claude AI...")
    try:
        test_cases = generate_test_cases(full_input)
        print(f"      ✓ Generated {len(test_cases)} test cases")
    except Exception as e:
        print(f"      ✗ AI generation failed: {e}")
        return

    # Step 4: Log each test case to Jira
    print(f"\n[4/4] Logging test cases to Jira under {story_key}...")
    logged, failed = [], []

    for i, tc in enumerate(test_cases, 1):
        try:
            result = jira.create_test_case(story_key, tc)
            key = result["key"]
            logged.append((key, tc["title"]))
            print(f"      ✓ [{i}/{len(test_cases)}] {key} — {tc['title']}")
        except Exception as e:
            failed.append(tc["title"])
            print(f"      ✗ [{i}/{len(test_cases)}] FAILED — {tc['title']}: {e}")

    # Summary
    _separator()
    print(f"\n  DONE")
    print(f"  Story       : {story_key} — {story_summary}")
    print(f"  Logged      : {len(logged)} test cases")
    if failed:
        print(f"  Failed      : {len(failed)} test cases")
    print(f"\n  View in Jira: https://divami.atlassian.net/browse/{story_key}")
    _separator()


def cmd_log_bug(story_key: str | None, spec_file: str | None):
    _separator()
    print("  LOG BUG TO JIRA")
    _separator()

    # Read bug description
    if spec_file:
        try:
            with open(spec_file) as f:
                raw_description = f.read().strip()
            print(f"\n✓ Loaded bug description from: {spec_file}")
        except Exception as e:
            print(f"✗ Could not read file: {e}")
            return
    else:
        raw_description = _read_multiline("\nDescribe the bug:")

    if not raw_description:
        print("✗ No description provided. Exiting.")
        return

    # AI parses the bug
    print("\n[1/2] Parsing bug description with Claude AI...")
    try:
        parsed = parse_bug(raw_description)
        print(f"      ✓ Summary  : {parsed['summary']}")
        print(f"      ✓ Severity : {parsed.get('severity', 'Medium')}")
        print(f"      ✓ Priority : {parsed.get('priority', 'Medium')}")
        print(f"      ✓ Category : {parsed.get('suggested_category', 'Functional')}")
    except Exception as e:
        print(f"      ✗ AI parsing failed: {e}")
        return

    # Build Jira bug
    print("\n[2/2] Creating bug in Jira...")
    from config import settings

    description_body = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Description"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": parsed["description"]}]},
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Steps to Reproduce"}]},
            {"type": "orderedList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": s}]}]}
                for s in parsed.get("steps_to_reproduce", [])
            ]},
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Expected Result"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": parsed["expected_result"]}]},
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Actual Result"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": parsed["actual_result"]}]},
        ]
    }

    payload = {
        "fields": {
            "project": {"key": settings.jira_project_key},
            "issuetype": {"name": "Bug"},
            "summary": parsed["summary"],
            "description": description_body,
            "priority": {"name": parsed.get("priority", "Medium")},
        }
    }

    try:
        result = jira.create_issue(payload)
        bug_key = result["key"]

        if story_key:
            try:
                jira.link_issues(bug_key, story_key, "Relates")
            except Exception:
                pass

        _separator()
        print(f"\n  DONE")
        print(f"  Bug Key  : {bug_key}")
        print(f"  Summary  : {parsed['summary']}")
        if story_key:
            print(f"  Linked to: {story_key}")
        print(f"\n  View in Jira: https://divami.atlassian.net/browse/{bug_key}")
        _separator()

    except Exception as e:
        print(f"      ✗ Jira API error: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="QA AI Agent — log test cases and bugs to Jira from your terminal",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # test-cases command
    tc = subparsers.add_parser(
        "test-cases",
        help="Generate test cases from product spec and log them to Jira"
    )
    tc.add_argument("story_key", help="Jira story key, e.g. IIRM-1234 or SCRUM-5")
    tc.add_argument("--file", "-f", help="Path to a .txt file containing extra product spec")
    tc.add_argument("--jira-only", "-j", action="store_true",
                    help="Use the Jira ticket description only — no extra spec needed")

    # bug command
    bug = subparsers.add_parser(
        "bug",
        help="Log a bug to Jira from a plain-text description"
    )
    bug.add_argument("--story", "-s", help="Jira story key to link the bug to, e.g. IIRM-1234")
    bug.add_argument("--file", "-f", help="Path to a .txt file containing the bug description")

    args = parser.parse_args()

    if args.command == "test-cases":
        cmd_generate_test_cases(args.story_key, args.file, getattr(args, "jira_only", False))
    elif args.command == "bug":
        cmd_log_bug(getattr(args, "story", None), args.file)


if __name__ == "__main__":
    main()
