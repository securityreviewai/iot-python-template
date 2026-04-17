# Guardrail Selection Threat Map

Use this file when deciding which guardrail categories apply to the current task and which threat families should influence the shortlist.

The intent is not to produce a full threat model here. The intent is to make sure likely exploit paths influence which guardrails are fetched by id and enforced during implementation.

## How to use this map

1. Start from the feature or code change.
2. Infer the categories involved in the implementation.
3. Use the mappings below to identify likely threat families.
4. Shortlist guardrails that directly or adjacently mitigate those threats.
5. Fetch those guardrails with `get_guardrail_by_id`.

## STRIDE-style mappings for guardrail selection

### Spoofing

Usually maps to authentication and session-related controls.

Threat patterns to consider:

- identity-related attacks
- session and token attacks
- business-logic attacks leading to authentication bypass
- injection attacks leading to authentication bypass
- serialization attacks leading to authentication bypass
- cryptographic attacks leading to authentication bypass
- lapses in logging leading to authentication bypass
- client-side trust leading to authentication bypass

Categories commonly shortlisted:

- `authentication`
- `session_management`
- `cryptography`
- `logging`
- `client_side`
- `business_logic`
- `input_validation`
- `deserialization`

### Tampering

Usually maps to authorization, integrity, and unsafe state change controls.

Threat patterns to consider:

- broken object level access control patterns
- broken functional level access control patterns
- injection-driven authorization bypass
- serialization-driven authorization bypass
- business-logic-driven authorization bypass
- client-side trust leading to unauthorized state changes

Categories commonly shortlisted:

- `authorization`
- `tenant_isolation`
- `data_access`
- `business_logic`
- `logging`
- `input_validation`
- `deserialization`
- `client_side`

### Repudiation

Usually appears when spoofing and tampering are possible but the system cannot prove what happened.

Threat patterns to consider:

- weak or missing audit trails for auth and authorization decisions
- missing actor attribution on sensitive state changes
- mutable or incomplete event records
- inability to correlate session, actor, and resource changes

Categories commonly shortlisted:

- `logging`
- `monitoring`
- `authentication`
- `authorization`
- `admin_workflows`

### Information Disclosure

Usually maps to authorization, data exposure, logging, and unsafe client-side trust.

Threat patterns to consider:

- broken object level access control patterns
- broken functional level access control patterns
- injection-driven information disclosure
- serialization-driven information disclosure
- business-logic-driven information disclosure
- lapses in logging leading to disclosure
- client-side trust causing exposure of protected data

Categories commonly shortlisted:

- `authorization`
- `tenant_isolation`
- `data_access`
- `logging`
- `input_validation`
- `deserialization`
- `client_side`
- `output_encoding`

### Denial of Service

Usually maps to workload protection, parsing safety, quota controls, and expensive query behavior.

Threat patterns to consider:

- broken access control patterns that expose heavy operations
- injection or data-access paths that amplify resource consumption
- serialization-driven memory or parser exhaustion
- business-logic-driven abuse of expensive workflows
- logging lapses that hide repeated abuse

Categories commonly shortlisted:

- `rate_limiting`
- `input_validation`
- `file_uploads`
- `deserialization`
- `data_access`
- `network`
- `monitoring`
- `logging`
- `business_logic`

### Elevation of Privilege

Usually maps to authorization, role boundaries, trust decisions, and privileged workflow controls.

Threat patterns to consider:

- access control bypasses from broken object or function level access
- injection-based privilege escalation
- client-side induced privilege escalation
- serialization-induced privilege escalation
- business-logic-triggered privilege escalation
- logging lapses that conceal privilege abuse

Categories commonly shortlisted:

- `authorization`
- `tenant_isolation`
- `admin_workflows`
- `business_logic`
- `client_side`
- `input_validation`
- `deserialization`
- `logging`

## Fast examples

### Add password reset flow

Likely categories:

- `authentication`
- `session_management`
- `cryptography`
- `logging`
- `rate_limiting`

Likely threat families:

- spoofing
- repudiation
- information disclosure

### Add admin endpoint to change user role

Likely categories:

- `authorization`
- `tenant_isolation`
- `admin_workflows`
- `logging`
- `business_logic`

Likely threat families:

- tampering
- repudiation
- elevation of privilege
- information disclosure

### Add bulk import endpoint

Likely categories:

- `input_validation`
- `file_uploads`
- `deserialization`
- `data_access`
- `logging`
- `rate_limiting`

Likely threat families:

- tampering
- information disclosure
- denial of service

### Move entitlement checks to the frontend

Likely categories:

- `authorization`
- `client_side`
- `tenant_isolation`
- `logging`

Likely threat families:

- tampering
- information disclosure
- elevation of privilege

## Selection reminders

- A feature can require guardrails from multiple categories.
- Shortlist for exploit chains, not isolated weaknesses.
- Logging often matters because poor auditability can turn spoofing, tampering, or privilege abuse into repudiation.
- Client-side logic often needs server-side guardrails even if the visible change is in the UI.
- If no existing guardrail covers a realistic recurring threat, create an `ide_generated` guardrail and carry it into `ctm_sync`.
