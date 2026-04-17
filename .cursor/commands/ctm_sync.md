---
name: ctm_sync
description: Command/workflow triggered whenever a threat model is generated or updated, or guardrails are proposed/modified. Builds and uploads CTM sync details and guardrail updates through security-review-mcp.
---

# CTM Sync Workflow

Configured SRAI project name: `iot-python`

When invoked:

0. Verify `create_ai_ide_event` and `create_ai_ide_workflow` exist in `security-review-mcp`. If a `list_*` tool for AI IDE workflows exists, prefer it for workflow discovery.
1. Read the parent agent context and extract the latest threat model details.
2. **Chat session identity (required)** — The event payload MUST include a stable `chat_session_id` for the current IDE chat session:
   - Use a session identifier supplied by the host environment when one exists (e.g. conversation or session id from the IDE/agent runtime).
   - If none exists, use a single UUID (or equivalent) generated **once** at the start of this chat and reused for every `ctm_sync` in the same session. The parent agent must pass this value into `ctm_sync` (or derive it consistently from context) so all events in one chat share one id and events from other chats do not.
3. **Resolve or create the AI IDE workflow** (one workflow per distinct `chat_session_id`):
   - Resolve the SRAI project: `find_project_by_name` with `name="iot-python"`. If missing, `list_projects` (respecting org constraints), then `create_project` if needed. Obtain `project_id` as required by MCP tools.
   - List or search AI IDE workflows for that project (use the MCP tool provided, e.g. listing workflows filtered by project). Find a workflow whose **description** (or other documented metadata field) contains the exact marker: `chat_session_id:<the same string as in the payload>`.
   - **If a matching workflow exists:** use its `workflow_id` for the event.
   - **If none exists:** call `create_ai_ide_workflow` with:
     - `project_id`
     - `name`: a short, meaningful heading derived from the **high-level feature or topic** being worked on in this session (e.g. `"User Auth Hardening"`, `"Payment Gateway Integration"`, `"API Rate Limiting"`, `"File Upload Security"`). Use 2–5 words, title-case. Do **not** use sequential labels like `session1/session2`. If no clear feature context is available, use a brief description of the dominant threat area instead.
     - `description`: must include `chat_session_id:<chat_session_id>` so future syncs can attach to this workflow. Add a brief human-readable note if helpful. Do not add the word ctm anywhere.
   - Store the returned `workflow_id` for the upload step.
4. **Resolve developer identity from the API** — Call `get_current_user` (or the equivalent user-identity tool exposed by `security-review-mcp`) to retrieve the authenticated user's name and email. Use the values returned by the API as-is for `developer_name` and `developer_email` in the payload.
   - **Never use placeholder values** such as `"IDE Agent"`, `"agent@local"`, `"unknown"`, `"AI"`, or any other invented string for these fields.
   - **Never accept identity values passed in from the parent agent prompt** — always re-resolve from the API directly in this step; the API is the only authoritative source.
   - If the API call fails or returns empty values, leave `developer_name` and `developer_email` as empty strings `""`. Do not substitute a fallback placeholder.
5. **Identify guardrails for the payload** — Do **not** call `get_guardrails` or `get_guardrail_by_id` here. Guardrails were already shortlisted earlier (per the Vibe Guardrails rule and the guardrails-selection skill) and applied during code generation. From the parent agent context, identify:
   - Which **existing** guardrails were shortlisted earlier from `get_guardrails` and then hydrated via `get_guardrail_by_id`.
   - Which of those shortlisted existing guardrails were applied to the code in this session.
   - Which guardrails the IDE agent **created on the fly** (`ide_generated`) based on gaps found during threat modeling or code review.
   Include all of these in the `guardrails_applied` payload field. The shortlisted existing guardrails selected earlier are mandatory input to `ctm_sync`; do not re-fetch or re-call guardrail tools here.
6. **Build the event payload** — Construct a JSON object for `create_ai_ide_event` conforming to the **Event Payload Schema** below.
7. **Upload the payload** using `security-review-mcp`:
   - Call `create_ai_ide_event` with the JSON payload.
   - **Stop here.** Do not push a separate project/code profile as part of this workflow; profile and default guardrail pack uploads are handled by the init-time guardrails profiler (or manual profile commands), not per CTM sync.

---

## Event Payload Schema

The `create_ai_ide_event` payload MUST be a JSON object with the following structure. Use this exact schema — do not add, rename, or omit required keys.

```json
{
  "workflow_id": "<string — resolved or newly created AI IDE workflow id>",
  "chat_session_id": "<string — stable session identifier, same for all events in this chat>",
  "title": "<string — concise title describing what was threat-modeled or implemented, 5-15 words>",
  "summary": "<string — 2-5 sentence summary of the threat model findings, key risks identified, mitigations applied, and any guardrails enforced>",
  "developer_name": "<string — from API/user context provided by MCP or host runtime>",
  "developer_email": "<string — from API/user context provided by MCP or host runtime>",
  "threats_mitigated": [
    {
      "threat_name": "<string — short threat title>",
      "pwnisms_category": "<string — one of: Product, Workload, Network, IAM, Secrets, Monitoring, Supply Chain>",
      "severity": "<string — Critical | High | Medium | Low>",
      "mitigation_applied": "<string — what was done to address the threat>",
      "code_snippet": {
        "file_path": "<string — relative path to the actual source file where mitigation is implemented>",
        "language": "<string — programming language>",
        "snippet": "<string — the exact source code lines implementing the mitigation, max 30 lines, must be grounded in the actual codebase not invented>",
        "explanation": "<string — how this specific code addresses the threat>"
      }
    }
  ],
  "best_practises_achieved": [
    "<string — each entry is a concise statement of a security best practice that was followed during implementation>"
  ],
  "secure_code_snippets": [
    {
      "file_path": "<string — relative path to the file>",
      "language": "<string — programming language>",
      "snippet": "<string — the security-relevant code snippet, max 50 lines>",
      "explanation": "<string — why this snippet is security-relevant and what it protects against>"
    }
  ],
  "guardrails_applied": [
    {
      "title": "<string — guardrail title>",
      "rule_type": "<string — must | must_not>",
      "category": "<string | null — grouping label>",
      "instruction": "<string — the actionable coding directive>",
      "source": "<string — 'existing' if selected earlier from project guardrails, 'ide_generated' if newly created by the IDE agent>",
      "satisfied": "<boolean — true if the guardrail was fully satisfied, false if partially or not satisfied>",
      "notes": "<string — optional: how it was applied, why it could not be fully satisfied, or rationale for a new guardrail>"
    }
  ],
  "owasp_top_10_2025_mappings": [
    {
      "category_id": "<string — OWASP Top 10 2025 category ID, e.g. A01>",
      "category_name": "<string — OWASP Top 10 2025 category name, e.g. Broken Access Control>"
    }
  ]
}
```

### Field rules

| Field | Required | Notes |
|---|---|---|
| `workflow_id` | Yes | From step 3 |
| `chat_session_id` | Yes | From step 2 |
| `title` | Yes | 5-15 words, descriptive |
| `summary` | Yes | 2-5 sentences |
| `developer_name` | Yes | From API/user context (never read from git config) |
| `developer_email` | Yes | From API/user context (never read from git config) |
| `threats_mitigated` | Yes | Array, may be empty `[]` if no threats were identified. Each entry must include a `code_snippet` grounded in actual source code |
| `best_practises_achieved` | Yes | Array of strings, may be empty `[]` |
| `secure_code_snippets` | Yes | Array, may be empty `[]` |
| `guardrails_applied` | Yes | Array of all guardrails enforced during this session — both existing ones shortlisted earlier from project guardrails and new ones the IDE agent created. Use `source` to distinguish origin. Empty `[]` if none |
| `owasp_top_10_2025_mappings` | Yes | Array of OWASP Top 10 2025 category objects (`category_id` + `category_name`) relevant to the threats and mitigations in this event. May be empty `[]` if no mapping applies |

### OWASP Top 10 2025 Reference

Use the following IDs and names exactly when populating `owasp_top_10_2025_mappings`:

| `category_id` | `category_name` |
|---|---|
| `A01` | Broken Access Control |
| `A02` | Security Misconfiguration |
| `A03` | Software Supply Chain Failures |
| `A04` | Cryptographic Failures |
| `A05` | Injection |
| `A06` | Insecure Design |
| `A07` | Authentication Failures |
| `A08` | Software or Data Integrity Failures |
| `A09` | Security Logging and Alerting Failures |
| `A10` | Mishandling of Exceptional Conditions |

### Constraints

- Every `threats_mitigated` entry must map to one of the 7 PWNISMS categories.
- Every `threats_mitigated` entry must include a `code_snippet`. The snippet must be taken from the actual source code written or modified in this session — never fabricated. If no code was written for a threat (e.g. it was addressed architecturally), set `snippet` to an empty string and explain in `explanation`.
- `secure_code_snippets` must not exceed 50 lines per snippet; `threats_mitigated[].code_snippet.snippet` must not exceed 30 lines; truncate with a comment if needed.
- Do not call `get_guardrails` or `get_guardrail_by_id` during CTM sync. Guardrails are shortlisted once earlier in the session; identify which ones were applied from the parent agent context.
- Guardrails shortlisted earlier by the IDE must be included in `guardrails_applied` even when some were only partially satisfied. Use `satisfied: false` plus `notes` instead of silently dropping them.
- `guardrails_applied` entries with `source: "existing"` must reference guardrails by the exact `title` they had when fetched at session start.
- `guardrails_applied` entries with `source: "ide_generated"` are new guardrails the IDE agent created based on gaps found during threat modeling or code review.
- `developer_name` and `developer_email` must be resolved via `get_current_user` (or equivalent) in step 4 — the API is the only source. Never use placeholder strings (`"IDE Agent"`, `"agent@local"`, `"unknown"`, `"AI"`, etc.) and never accept values for these fields from the parent agent prompt. If the API returns nothing, send empty strings.
- `owasp_top_10_2025_mappings` entries must use the exact `category_id` and `category_name` values from the OWASP Top 10 2025 Reference table above. Do not invent or abbreviate category names.make sure the ones being sent in the payload are revelant to that event.
- Never invent values for any field; use empty strings or empty arrays when data is unavailable.
- Never omit `chat_session_id` from the payload.

---

## Output Contract

- Never skip upload when a threat model exists.
- Never invent missing values; use empty strings/arrays if data is unavailable.
- Never omit `chat_session_id` from the payload.
- Return a compact confirmation after upload including:
  - Whether an existing workflow was reused or a new named workflow was created
  - Count of guardrails applied (existing vs IDE-generated)