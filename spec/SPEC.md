# Proof-Carrying Pipelines — Specification (v1.0)

Status: Draft · License: Apache-2.0 · This document uses RFC 2119 keywords.

## 1. Roles

- **Producer** — an identified machine that executes gates locally.
- **Signer** — an organization-held asymmetric key (HSM/KMS RECOMMENDED). Producers hold
  *invocation rights*, never key material.
- **Verifier** — the attest-and-skip gate at the pipeline choke point.
- **Sources of truth** — repositories/registries defining gates, tool images and rule sets.

## 2. Attestation payload

The payload MUST be canonical JSON (JCS, RFC 8785) with exactly these fields:

```json
{
  "pcp": 1,
  "content": "<git tree hash of the attested state>",
  "tools": ["<oci image digest or binary sha256>", "..."],
  "rules": "<sha256 over the ordered rule-set documents>",
  "gates": ["<gate id>", "..."],
  "verdict": "PASS",
  "identity": "<enrolled principal, e.g. user@org>",
  "timestamp": "<RFC 3339 UTC>"
}
```

- `content` MUST be the **tree** hash, not the commit hash.
- An OPTIONAL `platform` object (`{os, arch, accelerator?, driver?}`) MAY be included for
  architecture-sensitive gates (e.g., CUDA workloads); when present, the verifier MUST
  check it against the approved platform set for those gates (extends V4). Gates whose
  outcome depends on hardware SHOULD assert thresholds rather than exact values.
- `verdict` MUST be `PASS`; failing runs MUST NOT be signed.
- The signature MUST cover the SHA-256 of the canonical payload.
- The attestation (payload + signature + key reference) SHOULD travel with the commit as a
  git note (`refs/notes/pcp`), commit trailer, or sidecar file.

## 3. Producer obligations

P1. Materialize gates from the sources of truth and record `versions.lock`
    (`{source revisions, tool digests, rules digest, locked_at, max_age}`).
P2. Execute every gate listed for the change set, using exactly the locked tool digests
    (container execution RECOMMENDED).
P3. Before signing, re-check the lock against the sources of truth. On drift or
    `now − locked_at > max_age`, the producer MUST NOT sign (advisory verdict) until updated.
P4. Sign only over a clean working tree whose tree hash equals `content`.

## 4. Verifier obligations

Given a delivery and an attestation, the verifier MUST check, in any order:

V1. Signature verifies against a key currently held by the Signer.
V2. `identity` ∈ current enrolled set (revocation honored at verify time).
V3. `content` = tree hash recomputed from the delivered state.
V4. every digest in `tools` ∈ currently approved set; `rules` = current rules digest.
V5. `now − timestamp ≤ TTL` (TTL RECOMMENDED ≤ 24h).

All pass ⇒ the verifier MAY elide gates ∈ `gates`. Any check fails, or no attestation exists
⇒ the verifier MUST run the full pipeline (**fail-closed**; absence of proof is the classic
path, never an error). Stages that are not redundant re-execution (registration, deployment,
environment-dependent tests) MUST NOT be elided.

## 5. Operational requirements

O1. Every signature MUST be audit-logged (who, when, which key).
O2. Elision MUST be revocable per identity without redeploying the pipeline.
O3. The organization SHOULD re-run a random sample of elided gate sets and alert on
    divergence (bounds fabricated-verdict survival; see threat A5 in the paper).
O4. Rule/tool rollout: bumping the approved digests at the verifier immediately invalidates
    all outstanding proofs — producers re-sync via their drift lock.

## 6. Non-goals

Formal proof of program properties; protection against a malicious producer who tampers with
local execution itself (requires TEE-backed signers, which MAY be used as producers);
acceleration of cold-start consumers.
