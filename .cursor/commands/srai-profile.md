---
name: srai-profile
description: Create and upload a SecurityReviewAI code profile using security-review-mcp
---

# SRAI Profile Uploader

Create a code profile from the current request and upload it to SRAI using `security-review-mcp`.

Configured SRAI project name: `iot-python`

## Steps

1. Determine scope from the user prompt.
   - If the request is about a specific capability/module/endpoint, produce a **Feature Code Profile**.
   - If the request is broad, exploratory, or architecture-level, produce a **Codebase Code Profile**.
2. Build detailed profile content before any upload call.
   - Include purpose, boundaries, entry points, sensitive data, trust boundaries, integrations, threats, controls, and open risks.
3. Resolve the SRAI project.
   - Use the configured project name by default; if it is missing or ambiguous, ask the user to confirm it.
   - Call `find_project_by_name` with `name="iot-python"`.
   - If missing, call `list_projects`; if still missing, call `create_project` with `name="iot-python"`.
4. Upload generated markdown content with tool 11: `upload_document`.
   - Use this for raw markdown/text generated in the chat.
   - Use a clear document name such as `feature-code-profile-<feature>.md` or `codebase-code-profile-<repo>.md`.
5. Upload files/diagrams with tool 10: `upload_document` when needed.
   - Provide base64 file content and file name.
   - Set `document_type` to `Component Diagram` for architecture diagrams.
   - Set `document_type` to `Uploaded Knowledgebase doc` for other document uploads.
6. Confirm the result.
   - Report project name, upload tool used, document name, and that processing is asynchronous.
   - If upload fails, return exact error details and next retry step.