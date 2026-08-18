# Proof-Carrying Pipelines (PCP)

**An architectural pattern for CI/CD in which pipeline gates execute on
untrusted-but-identified machines and their verdict travels with the commit as a
cryptographic attestation — bound to the exact content, tool digests and rule-set version,
signed under organizational key custody — so the pipeline can verify in seconds, skip
redundant re-execution, and fall back closed. The pattern's core exchange is specified as
the *attest-and-skip protocol* ([SPEC v1](spec/SPEC.md)).**

> The commit carries the evidence; the checker stays cheap.
> *(A deliberate homage to Proof-Carrying Code, Necula 1996.)*

## The pattern in 30 seconds

Modern pipelines re-run the same hermetic gates (lint, static analysis, policy checks,
compilation, unit tests) on shared cloud runners for every push — work the developer's idle,
already-paid-for machine just did. PCP makes the local run *count*:

1. **Pin** — a local bundle locks gate tooling to the org's sources of truth
   (tool image digests + rule-set digest + revisions).
2. **Execute** — gates run locally, in the same pinned containers the pipeline uses.
3. **Bind & sign** — on PASS, a canonical payload binds
   `content (git tree hash) × tool digests × rules digest × identity × timestamp`,
   signed by an **org-held KMS/HSM key** the machine can invoke but never possess.
4. **Attest-and-skip gate** — the pipeline verifies signature, enrolled identity, exact
   content, approved digests, current rules and freshness — in seconds — and elides the
   redundant gates.
5. **Fail closed** — any missing/stale/drifted/invalid proof ⇒ the full pipeline runs.
   PCP can never be less safe than classic CI.
6. **Drift lock** — a drifted or stale local bundle refuses to sign until it self-updates;
   bumping approved digests at the verifier instantly invalidates every outstanding proof.

**What you get:** minutes of queued runner time → one signature check; compute shifted to the
edge; contracts/rules still enforced centrally, with audit logs and per-identity revocation.
**What it is not:** a TEE. A malicious *enrolled* producer is bounded (pinned digests, audit
logs, sampled re-verification, revocation), not eliminated — see the threat model in the
[paper](paper/proof-carrying-pipelines.md) and the normative [SPEC](spec/SPEC.md).

## Try it (60 seconds, no cloud needed)

```bash
pip install cryptography pytest pyyaml
reference/demo/run_demo.sh
```

The demo creates a tiny repo, runs two gates, signs an attestation (local Ed25519 stand-in
for KMS), verifies it (**VERDICT: SKIP**), then tampers with the content and shows the
fail-closed fallback (**VERDICT: RUN FULL PIPELINE**).

## Repository layout

| Path | Contents |
|---|---|
| [`paper/proof-carrying-pipelines.md`](paper/proof-carrying-pipelines.md) | The whitepaper: motivation, related work, threat model, protocol, case study |
| [`docs/architecture.md`](docs/architecture.md) | C4 views (context, containers) + the attest-and-skip protocol as a sequence diagram — rendered natively by GitHub |
| [`docs/use-cases.md`](docs/use-cases.md) | Eight instantiations beyond CI/CD (ML training/compilation/promotion offload, IaC, vendor intake, regulated documents, fleets…) + the 4-point selection test |
| [`diagrams/`](diagrams/) | Mermaid sources + rendered PNGs of all diagrams |
| [`spec/SPEC.md`](spec/SPEC.md) | Normative spec: payload schema, producer/verifier obligations (V1–V5), operational rules |
| [`reference/pcp.py`](reference/pcp.py) | Reference CLI: `keygen · attest · verify` (Ed25519 demo backend + Google Cloud KMS backend) |
| [`reference/demo/`](reference/demo/) | Runnable end-to-end demo |
| [`.github/workflows/attest-and-skip.yml`](.github/workflows/attest-and-skip.yml) | Example CI wiring with fail-closed fallback |

## Prior art (and why PCP is different)

in-toto signs supply-chain step execution (verified end-of-chain, not for eliding CI work) ·
SLSA / sigstore / GitHub Artifact Attestations sign *provenance* · TEE approaches
(Attestable Builds '25; Castillo et al. '26) get stronger guarantees with hardware PCP
deliberately doesn't require · Nix/Trustix trust via determinism · build caches (Bazel/Nx/
Turbo) skip by hash but trust cache ACLs · Basecamp's `gh-signoff` is the cultural demand
signal — self-attestation with none of the binding. PCP names the missing middle: identity-
signed, content-bound, drift-locked, fail-closed **gate elision**. Full comparison in §2 of
the paper.

## Status & citation

v1.0 draft — feedback and PRs welcome. If you use or discuss the pattern, cite via
[`CITATION.cff`](CITATION.cff).

## License

Apache-2.0 © 2026 Jack Andrés Cid
