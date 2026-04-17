---
name: guardrails-init-profile
description: Run the Security Review Kit guardrails profiler — scan the repo, write profile.json, push profile and default guardrail pack to SecurityReview.ai via MCP.
---

# Guardrails init profile

Execute the workflow defined in **`.cursor/skills/guardrails-profiler/SKILL.md`** end-to-end in this workspace (this IDE’s copy of the guardrails-profiler skill).

Configured SRAI project name: `iot-python`

**You must:**

1. Read `.cursor/skills/guardrails-profiler/SKILL.md` and follow every step (use the signal registry at `.cursor/skills/guardrails-profiler/references/signal-registry.json`).
2. Write `.guardrails/profile.json` and **`profile.json`** at the project root as specified.
3. Call **`update_vibe_profile`** and **`write_default_pack`** on `security-review-mcp` after resolving `project_id` for `iot-python`.

Do not skip MCP upload when credentials and MCP are available.

Do **not** ask the user to verbally approve MCP for `security-review-mcp`. The init-time profiler runner passes the CLI-specific MCP configuration and approval settings where supported; call the MCP tools directly.

## Cursor CLI (scripted)

From the repo root, non-interactive runs should include workspace trust and MCP approval:

`agent -p "<your profiling instructions>" --trust --approve-mcps` (or `cursor-agent` if that is what your install provides)

Add `--output-format stream-json --stream-partial-output` only when you need verbose agent diagnostics (or use `securityreview-kit init` with `--profiler-verbose`).

During `securityreview-kit init`, choose **Yes** when asked to run Cursor login in-terminal, or pass **`--profiler-cursor-login`** with **`--profile-repo`** so login and profiling stay in one run.

You can still sign in manually with `agent login` (or `cursor-agent login`). To handle trust/login interactively in the terminal, omit `--trust` and `--approve-mcps`.

## Claude Code CLI (scripted)

From the repo root, non-interactive runs should execute with the project settings file, the project `.mcp.json` server config, explicit MCP-only loading, bypassed tool prompts for the profiling pass, and the Haiku model:

`claude -p "<your profiling instructions>" --settings .claude/settings.json --mcp-config "$(cat .mcp.json)" --strict-mcp-config --permission-mode bypassPermissions --model haiku`

During `securityreview-kit init`, choose **Yes** when asked to run Claude Code login, or pass **`--profiler-claude-login`** with **`--profile-repo`** so `claude auth login` and profiling stay in one run.

Claude profiling can also run with **Anthropic Console**, **ANTHROPIC_API_KEY**, an **Anthropic-compatible gateway** (`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`), or cloud-provider credentials such as **AWS Bedrock** and **Google Vertex AI**. `securityreview-kit init` can branch into those auth modes before profiling.

## GitHub Copilot CLI (scripted)

From the repo root, non-interactive runs should load the SRAI MCP server and allow the tools needed to scan, write profile files, and call MCP:

`copilot -p "<your profiling instructions>" --additional-mcp-config '{"mcpServers":{"security-review-mcp":{"type":"stdio","command":"npx","args":["-y","@securityreviewai/security-review-mcp@latest"]}}}' --allow-all`

During `securityreview-kit init`, choose **Yes** when asked to run GitHub Copilot CLI login, or pass **`--profiler-copilot-login`** with **`--profile-repo`** so `copilot login` and profiling stay in one run.

## Codex CLI (scripted)

From the repo root, non-interactive runs should execute via `codex exec` and include the SRAI MCP server configuration for that run.

During `securityreview-kit init`, choose **Yes** when asked to run Codex login, or pass **`--profiler-codex-login`** with **`--profile-repo`** so `codex login --device-auth` and profiling stay in one run.