---
name: PWNISMS Threat Modelling
description: Security-first threat modelling workflow for code and architecture tasks. Walks all 7 PWNISMS categories, enforces vibe guardrails (secure by code), and synchronizes findings via CTM sync. Use before, during, and after implementation.
---

# PWNISMS — Security-First Threat Modelling

For EVERY security-relevant task (feature, bug fix, refactor, infra change, architecture design), run a threat model with PWNISMS.

- Walk through all 7 categories explicitly.
- If a category is not applicable, state it briefly and move on.
- Anchor analysis to linked files, diffs, PRs, API specs, and diagrams whenever available.
- Focus on realistic threats for the current context, not exhaustive attack catalogs.

---

## Phase 0 — Guardrail Context

Before deep analysis, ensure the project-specific guardrail shortlist exists:

1. Use `.cursor/skills/guardrails-selection/SKILL.md`.
2. Resolve the project with `find_project_by_name` using `name="iot-python"`.
3. Call `get_guardrails`, shortlist intentionally for this task, then hydrate the exact shortlist with `get_guardrail_by_id`.
4. Keep the shortlisted existing guardrails in context for implementation and `ctm_sync`.

Do not perform project-profile exploration as part of PWNISMS. The old profile tools are not part of this workflow. Ground the threat model in the user request, repository code, diffs, architecture docs the user provides, and the shortlisted guardrails.

If SRAI is not available, proceed with the user-provided context and repository evidence, then clearly note that project guardrails could not be fetched.

---

## Phase 1 — Inputs to Gather

Collect these quickly before deep analysis:

- **Scope**: What is changing (feature, component, service, migration, PR)?
- **Assets**: What must be protected (PII, credentials, tokens, configs, accounts, workflows)?
- **Entry points**: How data enters/leaves (HTTP, queues, schedulers, CLI, webhooks, integrations)?
- **Trust boundaries**: Where data crosses users/services/networks/privilege levels?
- **Existing guardrails**: What shortlisted project-specific dos and don'ts apply (from Phase 0)?

If the user provided specific code, diffs, or architecture artifacts, prioritize those as primary evidence.

---

## Phase 2 — Lightweight Workflow (PWNISMS)

1. **Clarify scope and assumptions**
   - Define the exact unit of analysis.
   - State assumptions explicitly (auth model, deployment boundary, tenant model, etc.).

2. **Map assets and flows**
   - List high-value assets and critical data paths.
   - List entry points and exits across trust boundaries.
   - Note which assets are covered by existing guardrails and which are not.

3. **Walk all 7 PWNISMS categories**
   - Identify plausible threats for each category.
   - Keep findings concrete and contextual.
   - For each threat, check if an existing guardrail already addresses it.

4. **Prioritize**
   - Select the top 3-7 risks by impact and likelihood.
   - Factor in existing mitigations from the codebase, user-provided context, and guardrails.

5. **Mitigate**
   - Propose concrete, implementable controls for each prioritized risk.
   - Map mitigations to specific guardrails where applicable.
   - If a mitigation represents a recurring pattern, propose it as a new guardrail candidate.

6. **Summarize residual risk**
   - Call out remaining risk, trade-offs, and follow-up actions.
   - Call out unknowns instead of silently guessing.
   - Note guardrail gaps — security patterns not yet captured by any guardrail.

---

## The 7 Categories (What to Check)

### P — Product

Application and business-logic threats:

- Input validation, injection, insecure deserialization.
- Authorization gaps, privilege escalation, IDOR/BOLA.
- Business logic abuse, replay/race conditions, unsafe redirects.
- Error handling that leaks internals.
- **Guardrail check:** Are there `must` / `must_not` rules for input validation, authorization patterns, error handling?

### W — Workload

Compute and infrastructure threats:

- Insecure container/runtime posture, over-privileged workload identity.
- Weak host/orchestrator controls and segmentation.
- Insecure data storage/backups and DB configuration.
- Queue/broker abuse and poison-message handling gaps.
- **Guardrail check:** Are there rules for container security, data-at-rest encryption, workload identity?

### N — Network

Network and transport threats:

- Missing/weak TLS, insecure service-to-service communication.
- Exposed ports/endpoints and permissive ingress/egress.
- Weak segmentation or lateral movement paths.
- API-layer abuse controls missing (rate limits, request limits, CORS hardening).
- **Guardrail check:** Are there rules for TLS enforcement, CORS policy, rate limiting?

### I — IAM (Identity & Access Management)

Identity and authorization threats:

- Broken authentication controls and token validation.
- Missing least-privilege RBAC/ABAC.
- Service-to-service auth gaps.
- Escalation paths across users, roles, or services.
- **Guardrail check:** Are there rules for auth mechanisms, session management, privilege boundaries?

### S — Secrets

Credential and key management threats:

- Secrets in code, images, logs, CI output, or defaults.
- Weak rotation, revocation, or token lifetime policies.
- Over-shared secrets across components.
- Missing secret manager/KMS controls.
- **Guardrail check:** Are there `must_not` rules against hardcoded secrets, `must` rules for secret manager usage?

### M — Monitoring (Logging & Observability)

Detection and auditability threats:

- Missing logs for auth, authorization, admin/data access events.
- Sensitive data leakage in logs.
- Missing alerts for abuse indicators.
- Incomplete audit trails or weak log integrity.
- **Guardrail check:** Are there rules for what must be logged and what must not appear in logs?

### S — Supply Chain

Dependency and delivery threats:

- Unpinned/unverified dependencies and vulnerable packages.
- Third-party integration trust and scope overreach.
- CI/CD pipeline leakage or unreviewed build scripts.
- Unsigned/unprovenanced artifacts, missing SBOM.
- Treat AI-generated code as untrusted until validated.
- **Guardrail check:** Are there rules for dependency pinning, SBOM generation, artifact signing?

---

## Phase 3 — Guardrail Enforcement (Secure by Code)

After completing the PWNISMS analysis and before writing code:

1. **Review the shortlisted hydrated guardrails** produced by `.cursor/skills/guardrails-selection/SKILL.md`.
2. **Classify applicability** — For each shortlisted guardrail, determine if it applies to the current task.
3. **Apply during code generation:**
   - `must` rules → mandatory implementation requirements. Every applicable `must` guardrail must be satisfied.
   - `must_not` rules → hard prohibitions. Code must never violate an applicable `must_not` guardrail.
4. **Flag conflicts** — If a guardrail conflicts with the user's explicit instruction, flag it and ask for confirmation.
5. **Create new guardrails on the fly** — When PWNISMS analysis or code review reveals a recurring security pattern not captured by existing guardrails, create and apply it as a new guardrail (marked `source: "ide_generated"` in CTM sync). Include `title`, `rule_type` (must/must_not), `category`, `instruction`, and rationale in the notes.

---

## Phase 4 — Security-First Code Generation Rules

When implementing code, enforce these baseline controls alongside project guardrails:

1. Validate and constrain all untrusted input.
2. Parameterize all queries and command-like invocations.
3. Enforce least privilege for users, services, and workloads.
4. Never hardcode secrets; use managed secret stores.
5. Encrypt sensitive data in transit and at rest.
6. Log security-relevant actions without leaking secrets/PII.
7. Pin and verify dependencies and build artifacts.
8. Return safe user errors; keep sensitive diagnostics internal.
9. Add abuse protections (rate limits, lockouts, throttling) on exposed interfaces.

---

## Tailor for Architecture / Design Tasks

When discussing designs before code exists:

- Sketch a mental data flow: actors, data sent/received, storage, processing points.
- Mark trust boundaries explicitly (client-backend, backend-DB, service-service, cloud-third party).
- Identify where strong authentication/authorization is mandatory.
- Identify where encryption in transit and at rest is mandatory.
- Recommend concrete security patterns:
  - Parameterized queries / ORM for DB access.
  - Centralized authn/authz and role checks.
  - Secrets manager / KMS for credentials and keys.
  - mTLS or signed requests for service-to-service calls.
- Review existing guardrails for design-level constraints.

---

## Phase 5 — CTM Sync (Post Threat Modelling)

**MANDATORY:** After every threat modeling step that produces or modifies threat content, synchronize via `ctm_sync`.

### What triggers CTM sync

- New threat model generated (any form: scenarios, data flows, attack trees, PWNISMS analysis)
- Existing threat model updated or extended (new threats, refined mitigations, additional components)
- Guardrails applied during a code-generation task (existing or IDE-generated)

### What CTM sync uploads

The `ctm_sync` agent builds and pushes an event payload containing:

- **Threat model findings**: threats mitigated, PWNISMS categories, severities, mitigations applied
- **Best practices achieved**: security patterns followed during implementation
- **Secure code snippets**: security-relevant code with explanations
- **Guardrails applied**: all guardrails enforced during this session — both existing ones shortlisted earlier via `get_guardrails` + `get_guardrail_by_id` (`source: "existing"`) and new ones the IDE agent created on the fly (`source: "ide_generated"`), each with satisfaction status

### How to invoke

Use the host's `ctm_sync` agent/workflow with:
- A clear description of what was threat-modeled
- The `chat_session_id` for workflow routing
- Whether this is a new threat model or an update

See `.cursor/agents/ctm_sync.md` for the full workflow and payload schema.

---

## Post-Generation Checklist

Before finalizing output, confirm:

- [ ] Scope, assumptions, and trust boundaries were explicit.
- [ ] All 7 PWNISMS categories were checked (or marked N/A explicitly).
- [ ] Top risks were prioritized by impact and likelihood.
- [ ] Mitigations are concrete and actionable.
- [ ] Residual risk and follow-up actions are stated.
- [ ] Vibe guardrails were fetched and enforced (all applicable `must`/`must_not` rules satisfied).
- [ ] Guardrail compliance summary is included in the response (existing + IDE-generated).
- [ ] CTM sync was invoked to upload threat model and guardrail data.

If ANY box cannot be checked, you MUST flag the gap to the user with a specific remediation recommendation before finalizing the code.