---
name: guardrails-profiler
description: Profile a codebase to detect its technology stack and generate a guardrails profile for security-aware AI code generation, then publish the profile and default guardrail pack to SecurityReview.ai via security-review-mcp. Use when Security Review Kit init runs profiling, when `.guardrails/profile.json` is missing, or when the developer asks to profile or re-profile the project.
---

# Guardrails Profiler

Profile a codebase's technology stack, write `.guardrails/profile.json`, write a combined **`profile.json` in the project root**, and upload to SRAI using `update_vibe_profile` and `write_default_pack`.

Configured SRAI project name: `iot-python`

## Canonical paths

- **This skill & signal registry (read-only):** `.cursor/skills/guardrails-profiler/` — e.g. `.cursor/skills/guardrails-profiler`, `.github/skills/guardrails-profiler`, `.claude/skills/guardrails-profiler`, or `.codex/skills/guardrails-profiler` for Codex depending on where this file was installed.
- **Signal registry file:** `.cursor/skills/guardrails-profiler/references/signal-registry.json`
- **Local guardrails file:** `.guardrails/profile.json`
- **Combined manifest (project root):** `profile.json` — includes guardrails profile, vibe profile fields for MCP, and default pack payload

## When This Runs

1. **Kit init**: User opted in to profile the repo and push the default pack.
2. **First-run / missing profile**: No `.guardrails/profile.json` and guardrails are needed before threat modeling.
3. **Explicit re-profile**: Developer asks to refresh the profile.

## Quick Check: Should I Profile?

Before profiling, check if a profile already exists:

- If `.guardrails/profile.json` exists and has a valid `schema_version`: **SKIP** unless the developer asked to re-profile.
- If missing: **PROCEED**.

## Profiling Procedure

Follow these steps in order.

### Step 1: Locate the Project Root

The project root is the current working directory. Confirm with markers such as `.git/`, `package.json`, `go.mod`, etc.

### Step 2: Read the Signal Registry

Read `.cursor/skills/guardrails-profiler/references/signal-registry.json` (the copy next to this `SKILL.md`). Use its categories (`universal`, `languages`, `frameworks`, `auth_identity`, `ai_agent`, `infrastructure`, `ci_cd`, `cloud_compute`, `databases`, `messaging`, `api_protocols`, etc.) to map detected signals to guardrail pack IDs.

### Step 3: Scan for Signals

Same methodology as the upstream guardrails-profiler skill:

#### 3a. Manifest and Config File Detection

List files in the project root (1–2 levels deep). Detect manifests (`package.json`, `pyproject.toml`, `go.mod`, `pom.xml`, `Dockerfile`, `.github/workflows/`, `next.config.*`, etc.) per the registry.

#### 3b. Dependency Parsing

For each manifest found, read dependencies and match names against `dependency_signals` in the registry. Prefer manifests over extension-only guesses.

#### 3c. Content Signals (targeted only)

When needed, grep specific files (e.g. Terraform providers, K8s `apiVersion`, CloudFormation) — do not read the entire repository.

#### 3d. File Extension Fallback

If no manifest exists for a language, use dominant extensions as a last resort.

### Step 4: Assemble the Guardrails Profile Object

Build the object for `.guardrails/profile.json`:

```json
{
  "schema_version": "1.0",
  "project_name": "<directory name>",
  "profiled_at": "<ISO 8601 timestamp>",
  "profiled_by": "<ide or cli id, e.g. agent, cursor-agent, claude, codex>",
  "detection_summary": {
    "languages": [],
    "frameworks": [],
    "infrastructure": [],
    "databases": [],
    "auth": [],
    "ai_agent": [],
    "ci_cd": [],
    "cloud_compute": [],
    "messaging": [],
    "api_protocols": [],
    "mobile": false
  },
  "guardrail_packs": [],
  "pack_count": 0
}
```

Rules for `guardrail_packs`:

1. Always include `owasp-asvs`.
2. Include `owasp-masvs` if mobile stacks are detected (flutter, react-native, swift, objective-c, kotlin per registry).
3. Add language, framework, auth, AI, infra, CI/CD, cloud, DB, messaging, and API packs per registry matches.
4. Deduplicate and set `pack_count`.

Do **not** invent packs or signals; if the repo is empty, use universal baseline only and empty category arrays where appropriate.

### Step 5: Write `.guardrails/profile.json`

Create `.guardrails/` if needed and write the profile file.

### Step 6: Build `profile.json` (project root)

Write **`profile.json`** at the project root with **only** these parts:

```json
{
  "schema_version": "2.0",
  "srai_project_name": "iot-python",
  "guardrails_profile": {},
  "default_guardrail_pack": {
    "guardrail_packs": [],
    "pack_count": 0
  }
}
```

- Populate **`guardrails_profile`** with the **same object** written to `.guardrails/profile.json` (detection summary, packs, etc.).
- Populate **`default_guardrail_pack`** with the deduplicated `guardrail_packs` list (same ids as in `guardrails_profile`) and `pack_count`.

**Do not** add a separate `vibe_profile` block and do **not** populate narrative fields such as long `description`, `architecture_notes`, `tech_categories`, `user_groups`, `compliance_requirements`, or `language_stacks`. The server-facing “vibe” update is driven **only** from the technical **`guardrails_profile`** plus the default pack (see Step 7).

### Step 7: Upload to SecurityReview.ai (security-review-mcp)

1. Resolve `project_id`: `find_project_by_name` with `name="iot-python"`. If missing, follow existing kit rules (`list_projects`, `create_project`).

2. Call **`update_vibe_profile`** with `project_id` and arguments mapped **only** from **`profile.json.guardrails_profile`** (and any required `project_id` fields) per the MCP tool’s documented schema. Treat the guardrails detection object as the profile payload — **not** a separate prose vibe document.

3. Call **`write_default_pack`** with `project_id` and the payload from **`profile.json.default_guardrail_pack`** (match the MCP tool’s schema).

4. **MCP approval:** Do **not** ask the user to “approve MCP” or “say you approve” for `security-review-mcp`. Security Review Kit passes the configured MCP server and approval settings during init-time profiling where the CLI supports it (for example Cursor CLI permissions and Copilot CLI `--additional-mcp-config` / `--allow-all`). Invoke `find_project_by_name`, `update_vibe_profile`, and `write_default_pack` directly. If a call still fails with permissions, report the exact CLI permission error — not a conversational approval step.

5. Confirm success: paths written (`profile.json`, `.guardrails/profile.json`) and whether both MCP calls succeeded, or the exact error.

### Step 8: Report

Give a concise summary of detected stack, pack count, and upload status.

## Empty / New Repository Handling

If there are no signals:

1. Optionally read `.git/config` for hints.
2. Emit minimal profile: `owasp-asvs` only, empty summaries where appropriate.
3. Still write `profile.json` (minimal `guardrails_profile` + `default_guardrail_pack`) and attempt MCP calls.

## IDE-Specific Notes

When run from Cursor Agent CLI, GitHub Copilot CLI, Claude Code, or Codex CLI, set `profiled_by` to a stable id (`agent` or `cursor-agent`, `copilot`, `claude`, `codex`).
