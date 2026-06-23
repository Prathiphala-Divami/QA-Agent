from __future__ import annotations
import sys
import os
import re
import argparse

sys.path.insert(0, os.path.dirname(__file__))

import jira_client as jira
from ai_service import generate_test_cases, parse_bug, analyze_execution, detect_intent
from cycle_store import get_cycle, set_cycle


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sep():
    print("\n" + "─" * 60)


def _read_multiline(prompt: str) -> str:
    print(prompt)
    print("(Type your text. When done, type END on a new line and press Enter)\n")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _build_bug_payload(
    parsed: dict,
    story_key: str | None = None,
    cycle_name: str | None = None,
    tc_title: str | None = None,
) -> dict:
    """Build a Jira bug creation payload from a parsed bug dict."""
    from config import settings
    project_key = story_key.split("-")[0] if story_key else settings.jira_project_key

    extra_content = []
    if tc_title:
        extra_content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": f"Linked Test Case: {tc_title}"}],
        })
    if cycle_name:
        extra_content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": f"Test Cycle: {cycle_name}"}],
        })

    description_body = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Description"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": parsed.get("description", "")}]},
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Steps to Reproduce"}]},
            {"type": "orderedList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": s}]}]}
                for s in parsed.get("steps_to_reproduce", [])
            ]},
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Expected Result"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": parsed.get("expected_result", "")}]},
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Actual Result"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": parsed.get("actual_result", "")}]},
            *extra_content,
        ],
    }

    category = parsed.get("suggested_category", "Functional")
    labels = [f"category-{category.lower().replace('/', '-').replace(' ', '-')}"]
    if cycle_name:
        labels.append(f"cycle-{cycle_name.lower().replace(' ', '-')}")

    issuetype_name = jira.resolve_bug_issuetype(story_key) if story_key else "Bug"

    payload: dict = {
        "fields": {
            "project": {"key": project_key},
            "issuetype": {"name": issuetype_name},
            "summary": parsed["summary"],
            "description": description_body,
            "priority": {"name": parsed.get("priority", "Medium")},
            "labels": labels,
        }
    }
    return payload


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_generate_test_cases(story_key: str, spec_file: str | None, jira_only: bool = False):
    _sep()
    print(f"  GENERATE & LOG TEST CASES → {story_key}")
    _sep()

    print(f"\n[1/4] Fetching story {story_key} from Jira...")
    try:
        story_text = jira.fetch_story_text(story_key)
        issue = jira.get_issue(story_key)
        story_summary = issue["fields"].get("summary", "")
        print(f"      ✓ {story_summary}")
    except Exception as e:
        print(f"      ✗ Failed: {e}")
        return

    print("\n[2/4] Reading spec...")
    if jira_only:
        full_input = story_text
        print("      ✓ Using Jira description only")
    elif spec_file:
        try:
            with open(spec_file) as f:
                extra_spec = f.read().strip()
            print(f"      ✓ Loaded spec from: {spec_file}")
            full_input = f"{story_text}\n\nProduct Specification:\n{extra_spec}"
        except Exception as e:
            print(f"      ✗ Could not read file: {e}")
            return
    else:
        extra_spec = _read_multiline("\n      Paste your product spec below (or END to use Jira description only):")
        full_input = f"{story_text}\n\nAdditional Specification:\n{extra_spec}" if extra_spec else story_text

    print("\n[3/4] Generating test cases with Claude AI...")
    try:
        test_cases = generate_test_cases(full_input)
        print(f"      ✓ Generated {len(test_cases)} test cases")
    except Exception as e:
        print(f"      ✗ AI generation failed: {e}")
        return

    print(f"\n[4/4] Logging to Jira under {story_key}...")
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

    _sep()
    print(f"\n  DONE — {len(logged)} test cases logged under {story_key}")
    if failed:
        print(f"  Failed to log: {len(failed)}")
    print(f"  View: https://divami.atlassian.net/browse/{story_key}")
    _sep()


def cmd_log_bug(story_key: str | None, spec_file: str | None):
    _sep()
    print("  LOG BUG TO JIRA")
    _sep()

    if spec_file:
        try:
            with open(spec_file) as f:
                raw = f.read().strip()
            print(f"\n✓ Loaded from: {spec_file}")
        except Exception as e:
            print(f"✗ Could not read file: {e}")
            return
    else:
        raw = _read_multiline("\nDescribe the bug:")

    if not raw:
        print("✗ No description provided.")
        return

    print("\n[1/2] Parsing with Claude AI...")
    try:
        parsed = parse_bug(raw)
        print(f"      ✓ Summary  : {parsed['summary']}")
        print(f"      ✓ Severity : {parsed.get('severity', 'Medium')}")
        print(f"      ✓ Priority : {parsed.get('priority', 'Medium')}")
        print(f"      ✓ Category : {parsed.get('suggested_category', 'Functional')}")
    except Exception as e:
        print(f"      ✗ AI parsing failed: {e}")
        return

    print("\n[2/2] Creating bug in Jira...")
    try:
        payload = _build_bug_payload(parsed, story_key)
        result = jira.create_issue_for(story_key, payload) if story_key else jira.create_issue(payload)
        bug_key = result["key"]

        if story_key:
            try:
                jira.link_issues_for(story_key, bug_key, story_key, "Relates")
            except Exception:
                pass

        _sep()
        print(f"\n  DONE")
        print(f"  Bug Key  : {bug_key}")
        print(f"  Summary  : {parsed['summary']}")
        if story_key:
            print(f"  Linked to: {story_key}")
        from config import settings
        base = settings.jira2_base_url if story_key and story_key.split("-")[0].upper() in {"SCRUM"} else settings.jira_base_url
        print(f"  View: {base}/browse/{bug_key}")
        _sep()

    except Exception as e:
        print(f"      ✗ Jira error: {e}")


def cmd_test_cycle(story_key: str, cycle_name: str):
    _sep()
    print(f"  TEST CYCLE: {cycle_name}  →  {story_key}")
    _sep()

    existing = get_cycle(cycle_name)
    if existing and existing.get("story_key") == story_key:
        pending_count = sum(1 for tc in existing["test_cases"] if tc["status"] == "not_executed")
        print(f"\n  Resuming '{cycle_name}' — {pending_count} test case(s) remaining.")
        cycle_data = existing
    else:
        print(f"\n[1/2] Fetching test cases from Jira under {story_key}...")
        try:
            test_cases = jira.fetch_test_cases_for_story(story_key)
        except Exception as e:
            print(f"      ✗ Failed: {e}")
            return

        if not test_cases:
            print(f"      ✗ No sub-tasks found under {story_key}.")
            print(f"        Generate them first: python3 cli.py test-cases {story_key} --jira-only")
            return

        print(f"      ✓ Found {len(test_cases)} test case(s)")
        cycle_data = {
            "story_key": story_key,
            "test_cases": [{**tc, "status": "not_executed", "bug_key": None} for tc in test_cases],
        }
        set_cycle(cycle_name, cycle_data)

    test_cases = cycle_data["test_cases"]
    total = len(test_cases)
    pending = [(i, tc) for i, tc in enumerate(test_cases) if tc["status"] == "not_executed"]

    if pending:
        print(f"\n[2/2] Executing {len(pending)} of {total} test case(s)...\n")

        for i, tc in pending:
            _sep()
            print(f"\n  [{i + 1}/{total}] {tc['title']}")
            if tc.get("steps"):
                print(f"\n  Steps:\n{tc['steps']}")
            if tc.get("expected_result"):
                print(f"\n  Expected: {tc['expected_result']}")
            print()

            notes = input("  What happened? (describe result, or press Enter to skip): ").strip()
            if not notes:
                print("  — Skipped")
                continue

            try:
                analysis = analyze_execution(tc, notes)
            except Exception as e:
                print(f"  ✗ AI analysis failed: {e}")
                continue

            status = analysis.get("status", "failed")
            test_cases[i]["status"] = status

            if status == "passed":
                print("  ✓ PASSED")
            else:
                print("  ✗ FAILED — logging bug to Jira...")
                bug_data = analysis.get("bug") or {}
                if bug_data:
                    try:
                        payload = _build_bug_payload(bug_data, story_key, cycle_name, tc["title"])
                        result = jira.create_issue(payload)
                        bug_key = result["key"]
                        test_cases[i]["bug_key"] = bug_key
                        try:
                            jira.link_issues(bug_key, story_key, "Relates")
                        except Exception:
                            pass
                        print(f"    → Bug: {bug_key}  |  https://divami.atlassian.net/browse/{bug_key}")
                    except Exception as e:
                        print(f"    ✗ Bug logging failed: {e}")

            set_cycle(cycle_name, cycle_data)

    # Summary
    passed = sum(1 for tc in test_cases if tc["status"] == "passed")
    failed_tcs = [tc for tc in test_cases if tc["status"] == "failed"]
    skipped = sum(1 for tc in test_cases if tc["status"] == "not_executed")

    _sep()
    print(f"\n  SUMMARY — {cycle_name}")
    print(f"  Passed  : {passed}/{total}")
    print(f"  Failed  : {len(failed_tcs)}/{total}")
    if skipped:
        print(f"  Skipped : {skipped}/{total}")

    bugs = [tc["bug_key"] for tc in failed_tcs if tc.get("bug_key")]
    if bugs:
        print(f"  Bugs    : {', '.join(bugs)}")

    if failed_tcs:
        answer = input(f"\n  Create next cycle with {len(failed_tcs)} failed case(s)? [y/N]: ").strip().lower()
        if answer == "y":
            match = re.search(r"(\d+)\s*$", cycle_name)
            if match:
                next_num = int(match.group(1)) + 1
                next_name = cycle_name[: match.start()] + str(next_num)
            else:
                next_name = f"{cycle_name} 2"
            new_cases = [{**tc, "status": "not_executed", "bug_key": None} for tc in failed_tcs]
            set_cycle(next_name, {"story_key": story_key, "test_cases": new_cases})
            print(f"\n  ✓ Created '{next_name}' with {len(new_cases)} test case(s)")
            print(f"    Run: python3 cli.py test-cycle {story_key} --name \"{next_name}\"")

    _sep()


# ── Natural Language Routing ───────────────────────────────────────────────────

def _handle_nl(prompt: str):
    print("\n  Detecting intent...", end="", flush=True)
    try:
        parsed = detect_intent(prompt)
    except Exception as e:
        print(f"\n  ✗ Could not parse prompt: {e}")
        return

    intent = parsed.get("intent")
    story_key = parsed.get("story_key")
    cycle_name = parsed.get("cycle_name") or "Build 1"
    spec_file = parsed.get("spec_file")
    use_jira_only = parsed.get("use_jira_only", True)

    print(f" → {intent}")

    if not story_key:
        story_key = input("  Story key (e.g. IIRM-9566): ").strip()
    if not story_key:
        print("  ✗ Story key required.")
        return

    if intent == "test-cases":
        cmd_generate_test_cases(story_key, spec_file, use_jira_only or not spec_file)
    elif intent == "bug":
        cmd_log_bug(story_key, spec_file)
    elif intent == "test-cycle":
        cmd_test_cycle(story_key, cycle_name)
    else:
        print(f"  ✗ Unknown intent '{intent}'. Try: test-cases, bug, or test-cycle.")


# ── Main ───────────────────────────────────────────────────────────────────────

KNOWN_COMMANDS = {"test-cases", "bug", "test-cycle"}


def main():
    # Natural language mode: first arg is not a subcommand
    if len(sys.argv) >= 2 and sys.argv[1] not in KNOWN_COMMANDS and not sys.argv[1].startswith("-"):
        _handle_nl(" ".join(sys.argv[1:]))
        return

    parser = argparse.ArgumentParser(
        description="QA AI Agent — generate test cases, log bugs, and run test cycles",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # test-cases
    tc = subparsers.add_parser("test-cases", help="Generate test cases from a Jira story and log them")
    tc.add_argument("story_key", help="Jira story key, e.g. IIRM-9566")
    tc.add_argument("--file", "-f", help="Path to extra spec .txt file")
    tc.add_argument("--jira-only", "-j", action="store_true", help="Use Jira description only")

    # bug
    bug = subparsers.add_parser("bug", help="Log a bug from a plain-text description")
    bug.add_argument("--story", "-s", help="Jira story key to link the bug to")
    bug.add_argument("--file", "-f", help="Path to bug description .txt file")

    # test-cycle
    cyc = subparsers.add_parser("test-cycle", help="Run a test cycle against logged test cases in Jira")
    cyc.add_argument("story_key", help="Jira story key, e.g. IIRM-9566")
    cyc.add_argument("--name", "-n", default="Build 1", help="Cycle name (default: Build 1)")

    args = parser.parse_args()

    if args.command == "test-cases":
        cmd_generate_test_cases(args.story_key, args.file, getattr(args, "jira_only", False))
    elif args.command == "bug":
        cmd_log_bug(getattr(args, "story", None), args.file)
    elif args.command == "test-cycle":
        cmd_test_cycle(args.story_key, args.name)


if __name__ == "__main__":
    main()
