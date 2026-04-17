---
name: guardrails-selection
description: Analyze the developer request, infer the security categories and likely threats involved, shortlist the most relevant project guardrails, then hydrate the exact guardrails with get_guardrail_by_id before implementation. Use for every security-relevant code task before code is written and preserve the shortlist for CTM sync.
---

# Guardrails Selection

Configured SRAI project name: `iot-python`

Use this skill whenever code will be created or modified and the task has any security surface.

This skill exists to stop the IDE from treating the full `get_guardrails` result as an unstructured blob. The workflow is:

1. Understand the request deeply.
2. Infer which security categories are in play.
3. Predict the threats that might occur for this exact task.
4. Shortlist only the guardrails that mitigate those threats.
5. Fetch the exact shortlisted guardrails with `get_guardrail_by_id`.
6. Carry that same shortlist forward into implementation and `ctm_sync`.

Do not skip the analysis step. Do not rely on title-matching alone. Do not dump every guardrail into the final answer.

## Inputs You Must Analyze First

Before calling `get_guardrails`, extract the actual development intent from the prompt and surrounding code:

- What is being built, changed, fixed, or refactored?
- Which components are affected: API, UI, background jobs, auth flow, webhook, file upload, admin tooling, AI agent flow, infra code, data pipeline?
- Which trust boundaries are crossed?
- Which sensitive assets are touched: tokens, credentials, sessions, PII, tenancy boundaries, audit logs, secrets, internal APIs, signed URLs, payment state, workflow approvals?
- Which technologies and patterns are involved in the existing code?
- What abuse cases are plausible if this change is implemented poorly?

You are not only selecting guardrails for the obvious functionality. You are selecting guardrails for the threats that might materialize around that functionality.

## Category Inference Workflow

Derive a category set for the task before shortlisting guardrails. Common categories include:

- `authentication`
- `authorization`
- `session_management`
- `input_validation`
- `output_encoding`
- `secrets`
- `cryptography`
- `logging`
- `monitoring`
- `file_uploads`
- `deserialization`
- `data_access`
- `rate_limiting`
- `network`
- `client_side`
- `business_logic`
- `tenant_isolation`
- `admin_workflows`

Use both the user request and the codebase patterns to infer the category set. A task can involve multiple categories even if the prompt mentions only one feature.

Examples:

- “Add magic-link login” likely involves `authentication`, `session_management`, `cryptography`, `logging`, `rate_limiting`, and `client_side`.
- “Add org admin API to update member roles” likely involves `authorization`, `tenant_isolation`, `logging`, `business_logic`, and `data_access`.
- “Add CSV import” likely involves `input_validation`, `file_uploads`, `data_access`, `deserialization`, `logging`, and denial-of-service protections.
- “Add client-side token refresh” likely involves `authentication`, `session_management`, `client_side`, `logging`, and `cryptography`.

## Threat Mapping Requirement

After identifying categories, infer the threat families that might occur. Use the reference file at `.cursor/skills/guardrails-selection/references/category-threat-map.md` every time you need to reason about category-to-threat mapping.

Your goal is not to enumerate every possible weakness. Your goal is to pick the threats that should influence guardrail selection for this task.

At minimum, consider whether the task can create:

- authentication bypass
- authorization bypass
- privilege escalation
- information disclosure
- repudiation gaps
- denial of service
- unsafe client-side trust
- insecure logging or audit gaps
- injection-triggered security failures
- serialization-triggered security failures
- business-logic-triggered bypasses

The shortlist should be threat-led, not catalog-led.

## Guardrail Selection Procedure

### Step 1: Resolve the project and load the catalog

1. Call `find_project_by_name` with `name="iot-python"` to obtain `project_id`.
2. Call `get_guardrails` with `project_id`.

Treat `get_guardrails` as the broad catalog. Do not treat it as the final set of instructions.

Assume each returned guardrail includes the fields needed for selection, including a stable identifier for follow-up retrieval, plus:

- `title`
- `rule_type`
- `category`
- `instruction`

If an identifier is absent, fall back to the best available stable reference exposed by the tool, but prefer the real guardrail id whenever available.

### Step 2: Build a shortlist

Shortlist guardrails using all of the following:

- direct category match with the task
- mitigation value against the likely threats you inferred
- relevance to the technologies and code paths being touched
- support for adjacent controls that prevent bypass chains
- duplication removal

Do not select a guardrail only because it sounds generally useful. Select it because it materially constrains the risky part of the current task.

Examples:

- If the task touches login, token issuance, password reset, session refresh, or identity proofing, prioritize authentication, session, crypto, logging, and brute-force defense guardrails.
- If the task changes role checks, tenant scoping, admin APIs, resource ownership, or query filters, prioritize authorization, tenant isolation, data access, business-logic, and audit guardrails.
- If the task introduces parsing, uploads, template expansion, or object hydration, prioritize input validation, file handling, deserialization, and denial-of-service guardrails.
- If the task moves security decisions into the browser or mobile client, prioritize client-side trust, token storage, server-side revalidation, and privilege-boundary guardrails.

### Step 3: Hydrate exact shortlisted guardrails

For every shortlisted existing guardrail, call `get_guardrail_by_id` to retrieve the exact guardrail that will govern implementation.

- Use `get_guardrail_by_id` for the shortlisted ids only.
- If the tool supports batching, batch the shortlisted ids.
- If the tool only supports one id at a time, call it once per shortlisted id.

Implementation must be driven by the hydrated shortlist from `get_guardrail_by_id`, not by vague memory from the broad catalog listing.

### Step 4: Track the active shortlist in context

Maintain an explicit in-context list of the shortlisted existing guardrails that will govern the task. For each shortlisted existing guardrail, keep:

- `id`
- `title`
- `rule_type`
- `category`
- `instruction`
- `why_selected`

Also track any new guardrails created during the task as `ide_generated`.

This shortlist is the source of truth for the rest of the session.

## Implementation Rules

Once the shortlist is hydrated:

- Every applicable `must` guardrail is mandatory.
- Every applicable `must_not` guardrail is a hard prohibition.
- If two shortlisted guardrails appear to conflict, explain the conflict and resolve it before coding.
- If the task reveals a real gap not covered by the shortlisted existing guardrails, create an `ide_generated` guardrail and apply it immediately.

When deciding whether a guardrail applies, prefer security-preserving inclusion over risky omission. If it plausibly mitigates a realistic path to abuse for the current task, keep it in scope.

## CTM Sync Handoff Contract

`ctm_sync` must reuse the shortlist from this skill. It must not call `get_guardrails` or `get_guardrail_by_id` again.

Before `ctm_sync` is invoked, ensure the parent context clearly contains:

- the exact existing guardrails shortlisted earlier
- which of them were applied
- whether each one was satisfied
- any notes about partial compliance, conflicts, or rationale
- every `ide_generated` guardrail created during the task

If a guardrail was shortlisted but not fully satisfied, still include it in the handoff with `satisfied: false` and a note. Do not silently drop it.

## Selection Quality Bar

A good selection does all of the following:

- covers the feature’s real threat surface, not just its visible functionality
- captures adjacent controls that stop bypass chains
- avoids irrelevant noise
- produces a small, defensible set of guardrails that can actually guide implementation
- leaves `ctm_sync` with an exact list of what the IDE selected and enforced

If your shortlist feels generic, it is probably incomplete or over-broad. Re-check the prompt, the code patterns, and the threat map.
