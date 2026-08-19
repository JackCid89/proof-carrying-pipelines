# Roadmap

Prioritized from adoption feedback. Issues welcome against any item.

1. **Merkle aggregation for monorepos** — promote the §4 design sketch to normative
   SPEC text + reference implementation: one payload per affected target, one KMS
   signature over the Merkle root, per-target inclusion proofs at the verifier.
   Without it, per-target KMS cost and audit-log noise scale poorly exactly where the
   pattern is most valuable.
2. **in-toto / DSSE export (O9)** — `pcp export` emitting the attestation as an
   in-toto Statement with a PCP predicate type, so transparency logs and policy
   engines can consume proofs.
3. **Transparency-log countersigning** — anchor payload digests in Rekor (or
   equivalent) to make attestation history append-only; completes the transport
   story of SPEC §5a for audit-evidence use cases.
4. **Adaptive sampling reference (O8)** — a small verifier-side state store scoring
   per-identity divergence and escalating sampling to quarantine.
5. **Agent-loop pilot** — implement the MCP `validate`/`attest` tools over the bundle
   and measure whether sensor fidelity + integrity reduces reward hacking and CI
   failure rates in practice (see docs/agent-loop.md, Validation status).
6. **Drift-lock background pre-fetch (O10)** — daemon/scheduled `pcp update`.
7. **TEE-backed signer backend** — drop-in stronger producer for A5-intolerant
   environments.
