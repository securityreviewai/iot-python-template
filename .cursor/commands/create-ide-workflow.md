---
name: create-ide-workflow
description: Create an AI IDE workflow in SRAI via security-review-mcp.
---

# Create IDE Workflow

Use `security-review-mcp` to create a workflow by calling:

- `create_ai_ide_workflow`

Required payload fields:

- `project_id`
- `name`
- `description`

## Steps

1. Resolve `project_id`.
   - Use configured project name `iot-python` by default.
   - Call `find_project_by_name` with `name="iot-python"`.
   - If not found, call `list_projects` and select the right project.
2. Build `name` and `description` from the user request.
   - Keep `name` short and action-oriented.
   - Keep `description` specific about trigger and output.
3. Call `create_ai_ide_workflow` with:
   - `project_id`
   - `name`
   - `description`
4. Return a concise confirmation including:
   - project id
   - workflow name
   - workflow id from MCP response (if returned)