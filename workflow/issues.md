# Issues Skill

## Purpose

Create a GitHub Issue that follows the standard Issue structure defined in `workflow/data/issues.json` and rendered by `workflow/template/issues_template.md`.

## Issue Structure

Every Issue must contain:

- `Title`: string
- `Description.Main.Task`: string
- `Description.Main.Requirements`: list of strings
- `Description.Main.Checklist`: list of strings

All fields under `Description.Main` are required.

## Rules

1. One Issue must do exactly one thing. `Task` must describe one clear task.
2. `Requirements` must contain one or more conditions that define what the task must satisfy.
3. `Checklist` must contain one or more concrete items used to verify that the task is complete.
4. If the Issue produces an output, the output must be represented as a Checklist item rather than a separate `Output` field.
5. Do not add parent/child relationship fields. Issue relationships are managed separately.
6. Do not add custom status fields. GitHub Issue `open` / `closed` is the completion state.
7. Father Issues and Child Issues use exactly the same Issue structure.

## Creating an Issue

When creating an Issue:

1. Determine the single task the Issue needs to accomplish.
2. Write a clear `Title`.
3. Write the `Task` as one concise task statement.
4. Add all required conditions to `Requirements`.
5. Add concrete verification points to `Checklist`.
6. Render the content using `workflow/template/issues_template.md`.
7. Create the GitHub Issue.

## Completion

An Issue is complete when its Checklist has been satisfied and the Human closes the GitHub Issue.

The AI must not create additional status fields to represent completion.
