# Issues Skill

## Purpose

Create a GitHub Issue that follows the standard Issue structure defined in `workflow/data/issues.json` and rendered by `workflow/template/issues_template.md`.

## Issue Structure

Every Issue must contain:

- `Title`: string
- `Description.Main.Task`: string
- `Description.Main.Requirements`: list of strings
- `Description.Main.Checklist`: list of strings

All fields under `Description.Main` are required. `workflow/data/issues.json` is a human-readable reference for this structure only (not machine-validated). The actual enforcement (rejecting unknown fields and empty lists) lives in `workflow/script/issues.py` and must be kept in sync with the Rules below.

## Rules

1. One Issue must do exactly one thing. `Task` must describe one clear task.
   - Cannot be checked by script. The AI must self-check this before creating the Issue: if `Task` could be split into two independently closable tasks, split it into separate Issues instead.
2. `Requirements` must contain one or more conditions that define what the task must satisfy.
   - Enforced by the schema (`minItems: 1`).
3. `Checklist` must contain one or more concrete items used to verify that the task is complete.
   - Enforced by the schema (`minItems: 1`).
4. If the Issue produces an output, the output must be represented as a Checklist item rather than a separate `Output` field.
   - Adding a separate `Output` field is enforced against by the schema (`additionalProperties: false`). Whether the output was *correctly* turned into a Checklist item is a semantic judgment the AI must self-check.
5. Do not add parent/child relationship fields. Issue relationships are managed separately.
   - Enforced by the schema (`additionalProperties: false`).
6. Do not add custom status fields. GitHub Issue `open` / `closed` is the completion state.
   - Enforced by the schema (`additionalProperties: false`).
7. Father Issues and Child Issues use exactly the same Issue structure.
   - Enforced by validating every Issue against the same schema, regardless of whether it is a parent or child.

## Creating an Issue

When creating an Issue:

1. Ask the Human which repository (`owner/repo`) this Issue should be created in. Do not guess or reuse a repository from a previous session without confirming. Use this repository for every `gh issue create` / API call in this task.
2. Determine the single task the Issue needs to accomplish.
3. Write a clear `Title`.
4. Write the `Task` as one concise task statement.
5. Add all required conditions to `Requirements`.
6. Add concrete verification points to `Checklist`.
7. Write the drafted data to a temporary JSON file matching the structure in `workflow/data/issues.json` (see the `structure` example there).
8. Run `python workflow/script/issues.py validate <draft-file>`. If it reports any error, fix the draft and re-run until it prints `VALID`. Do not proceed to the next step until validation passes.
9. Re-check Rules 1 and 4 by hand (they cannot be validated by the script — see the Rules section above).
10. Render the content using `workflow/template/issues_template.md`.
11. Create the GitHub Issue in the repository confirmed in step 1.

## Completion

An Issue is complete when:

1. Its Checklist has been satisfied and the Human closes the GitHub Issue, and
2. `workflow/data/issues.log` shows `"status": "ok"` for that Issue number. This is written automatically by the `Validate Issue Structure` GitHub Action whenever the Issue is opened or edited, and must be reviewed by the Human — a `"status": "error"` entry means the created Issue drifted from the schema (e.g. a field was fabricated or a section was dropped when it was rendered) and needs to be fixed.

The AI must not create additional status fields to represent completion.
