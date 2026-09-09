"""Issue workflow utilities.

Two commands:

1. validate    - validate a drafted issue JSON file against the structure
                 rules below before the Issue is created.
2. check-issue - reverse-parse a rendered GitHub Issue body (from a GitHub
                 Actions "issues" event payload) back into structured data,
                 validate it with the same rules, and record the result in
                 workflow/data/issues.log.

The rules encoded here mirror workflow/issues.md exactly. workflow/data/issues.json
stays a plain human-readable structure reference; it is NOT parsed as a schema.
If the Rules section in issues.md changes, update ALLOWED_*/REQUIRED_* below
to match.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # workflow/
LOG_PATH = ROOT / "data" / "issues.log"

CHECKLIST_ITEM_RE = re.compile(r"^-\s*\[[ xX]\]\s*(.+)$")
BULLET_ITEM_RE = re.compile(r"^-\s*(.+)$")
HEADING_RE = re.compile(r"^##\s*(.+?)\s*$")

# --- Structure rules, hardcoded to match workflow/issues.md ----------------
ALLOWED_TOP_FIELDS = {"Title", "Description"}
REQUIRED_TOP_FIELDS = {"Title", "Description"}

ALLOWED_DESCRIPTION_FIELDS = {"Main"}
REQUIRED_DESCRIPTION_FIELDS = {"Main"}

# Rules 4/5/6: no Output / Status / Parent / Child fields, or anything else
# beyond Task/Requirements/Checklist, under Description.Main.
ALLOWED_MAIN_FIELDS = {"Task", "Requirements", "Checklist"}
REQUIRED_MAIN_FIELDS = {"Task", "Requirements", "Checklist"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_issue_data(data: dict) -> list[str]:
    """Check `data` against the structure rules in workflow/issues.md.

    Returns a list of human-readable error strings; empty list means valid.
    Does NOT check Rule 1 (single task) or the semantic half of Rule 4
    (output correctly turned into a Checklist item) - those need human/AI
    judgment and are handled as a manual self-check step in issues.md.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["<root>: expected a JSON object"]

    for key in REQUIRED_TOP_FIELDS:
        if key not in data:
            errors.append(f"{key}: missing required field")
    for key in data:
        if key not in ALLOWED_TOP_FIELDS:
            errors.append(f"{key}: field is not allowed (Rules 5/6)")

    title = data.get("Title")
    if "Title" in data and (not isinstance(title, str) or not title.strip()):
        errors.append("Title: must be a non-empty string")

    description = data.get("Description")
    if "Description" in data:
        if not isinstance(description, dict):
            errors.append("Description: expected an object")
        else:
            for key in REQUIRED_DESCRIPTION_FIELDS:
                if key not in description:
                    errors.append(f"Description.{key}: missing required field")
            for key in description:
                if key not in ALLOWED_DESCRIPTION_FIELDS:
                    errors.append(f"Description.{key}: field is not allowed (Rules 5/6)")

            main = description.get("Main")
            if "Main" in description:
                if not isinstance(main, dict):
                    errors.append("Description.Main: expected an object")
                else:
                    for key in REQUIRED_MAIN_FIELDS:
                        if key not in main:
                            errors.append(f"Description.Main.{key}: missing required field")
                    for key in main:
                        if key not in ALLOWED_MAIN_FIELDS:
                            errors.append(
                                f"Description.Main.{key}: field is not allowed "
                                "(Rules 4/5/6 - no Output/Status/Parent/Child fields)"
                            )

                    task = main.get("Task")
                    if "Task" in main and (not isinstance(task, str) or not task.strip()):
                        errors.append("Description.Main.Task: must be a non-empty string")

                    for field_name in ("Requirements", "Checklist"):
                        if field_name not in main:
                            continue
                        value = main[field_name]
                        if not isinstance(value, list):
                            errors.append(f"Description.Main.{field_name}: expected a list")
                            continue
                        if len(value) < 1:
                            rule = "Rule 2" if field_name == "Requirements" else "Rule 3"
                            errors.append(
                                f"Description.Main.{field_name}: must contain at least "
                                f"1 item ({rule})"
                            )
                        for index, item in enumerate(value):
                            if not isinstance(item, str) or not item.strip():
                                errors.append(
                                    f"Description.Main.{field_name}[{index}]: must be a non-empty string"
                                )

    return errors


# ---------------------------------------------------------------------------
# Reverse-parse a rendered issue body (workflow/template/issues_template.md
# output) back into structured data, so a created/edited GitHub Issue can be
# checked with the same rules used before creation.
# ---------------------------------------------------------------------------

def parse_rendered_body(body: str) -> dict:
    sections: dict[str, list[str]] = {"任务": [], "要求": [], "验收条件": []}
    current: str | None = None

    for raw_line in body.splitlines():
        line = raw_line.strip()
        heading_match = HEADING_RE.match(line)
        if heading_match:
            heading = heading_match.group(1)
            current = heading if heading in sections else None
            continue
        if current is None or not line:
            continue
        sections[current].append(line)

    task = " ".join(sections["任务"]).strip()

    requirements = []
    for line in sections["要求"]:
        match = BULLET_ITEM_RE.match(line)
        if match:
            requirements.append(match.group(1).strip())

    checklist = []
    for line in sections["验收条件"]:
        match = CHECKLIST_ITEM_RE.match(line)
        if match:
            checklist.append(match.group(1).strip())

    return {
        "Description": {
            "Main": {
                "Task": task,
                "Requirements": requirements,
                "Checklist": checklist,
            }
        }
    }


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    errors = validate_issue_data(data)

    if errors:
        print("INVALID - the drafted Issue does not satisfy workflow/issues.md:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("VALID - the drafted Issue satisfies the structure rules.")
    return 0


def _write_log_record(record: dict) -> None:
    log: dict = {}
    if LOG_PATH.exists() and LOG_PATH.read_text(encoding="utf-8").strip():
        log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    log[str(record["issue_number"])] = record
    LOG_PATH.write_text(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def cmd_check_issue(args: argparse.Namespace) -> int:
    event_path = args.event_file or os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).exists():
        print("Error: no GitHub Actions event payload found (--event-file or $GITHUB_EVENT_PATH)", file=sys.stderr)
        return 2

    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    issue = event.get("issue")
    if not issue:
        print("Error: event payload does not contain an 'issue' object", file=sys.stderr)
        return 2

    number = issue["number"]
    title = issue.get("title", "")
    body = issue.get("body") or ""

    data = parse_rendered_body(body)
    data["Title"] = title

    errors = validate_issue_data(data)

    record = {
        "issue_number": number,
        "title": title,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if not errors else "error",
        "errors": errors,
    }
    _write_log_record(record)

    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue workflow utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate a drafted issue JSON file before creating the Issue."
    )
    validate_parser.add_argument("file", help="Path to the drafted issue JSON file")
    validate_parser.set_defaults(func=cmd_validate)

    check_parser = subparsers.add_parser(
        "check-issue",
        help="Reverse-parse and validate a GitHub Issue from a GitHub Actions event payload.",
    )
    check_parser.add_argument(
        "--event-file",
        default=None,
        help="Path to the event JSON file (defaults to $GITHUB_EVENT_PATH)",
    )
    check_parser.set_defaults(func=cmd_check_issue)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
