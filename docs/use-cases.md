# PCP beyond CI/CD — use cases

The pattern generalizes to any system with this shape: **a central choke point re-executes
verification that identified edge nodes already performed**, because it cannot trust that
the work happened, over that exact content, with the current tools and rules. Wherever
those three facts can be bound and signed more cheaply than re-execution, PCP applies.

For each case: who produces, what the gates are, what gets elided, and the caveat that
matters. Everything environment-dependent stays at the choke point (SPEC §4) — PCP elides
only *hermetic* verification.

---

## 1. Data platforms: contracts, models and pipeline definitions *(the origin)*

**Producer:** data engineer's workstation. **Gates:** data-contract structural validation,
SQL model rule checks, DAG static analysis, compile + unit tests — in the platform's own
validator containers. **Elided:** the re-validation stages of the platform's CI; runtime
data-quality tests still run on every execution (they depend on data, not code).
**Caveat:** rule catalogs change often — the drift lock is what makes this safe, and rule
rollout doubles as instant proof invalidation.

## 2. ML: training, model compilation and promotion

**Producer:** researcher's workstation, on-prem GPU rig, or a training-cluster node — any
enrolled machine whose hardware matches the approved platform set (the payload binds
`platform`: arch, accelerator, driver — SPEC §2). Three workloads move, in increasing
order of ambition:

- **Promotion gates** *(the classic case)*: eval suites on pinned benchmark datasets
  (dataset digests in `tools`), bias/regression thresholds, model-card completeness,
  license scans. **Elided:** the registry's re-evaluation before promoting to staging.
- **Model compilation**: TensorRT engine builds, `torch.compile`/AOT artifacts, ONNX
  export, quantization. Hermetic *with respect to the platform* — outcome is a function of
  content × tool digests × hardware — so it qualifies when the verifier enforces platform
  equivalence (extends V4). **Elided:** the pipeline's re-compilation and artifact
  validation pass.
- **Training runs**: the attestation binds the exact recipe — code tree, dataset digests,
  hyperparameters (all part of `content`/`tools`), platform and identity — so downstream
  promotion can trust *that this artifact came from that recipe* without re-running it.
  This is PCP-as-provenance more than PCP-as-elision: the pipeline was never going to
  re-train per push, but the signed binding replaces "trust the researcher's word" with a
  verifiable, revocable claim. Binding the produced artifact's digest into the payload
  extends this to attested artifact reuse (PCP + cache).

**Limitations — training especially:**

1. *Nondeterminism*: identical inputs do not yield identical bits on GPUs (kernel
   autotuning, atomics, cuDNN heuristics). Gates MUST assert thresholds — eval metrics,
   convergence criteria — never exact weights or exact engine bits.
2. *Sampling is expensive*: O3's sampled re-execution, the main bound on a lying producer,
   costs a full retrain here. Sample cheap proxies instead (re-run evals on the delivered
   artifact, re-verify data digests) and reserve full retrain audits for high-stakes models.
3. *Data gravity and privacy*: dataset digests must be computable where the producer runs,
   and regulated data may not be allowed to move — then move the producer to the data
   (on-prem is fine: PCP binds identity and platform, not location).
4. *Long runs vs freshness*: sign at completion over a clean tree (P4); a multi-day run
   whose base drifted must rebase and re-validate before signing, and the TTL (V5) starts
   at the signature, not at job start.
5. *Higher residual*: a fabricated training claim is costlier to catch than a fabricated
   lint verdict. Keep eval-based acceptance gates centralized in the pipeline — elide
   redundant *re-verification*, never blind-accept model quality.

**Caveat:** this is the pattern's most valuable and most adversarial instance at once —
adopt promotion gates first, compilation second, training attestation last.

## 3. Infrastructure-as-Code and policy-as-code

**Producer:** platform engineer's machine. **Gates:** `terraform validate` + plan against
policy engines (OPA/Sentinel rule-set digest = `rules`), cost guardrails, forbidden-resource
scans. **Elided:** the plan-and-scan stage of the CD pipeline; `apply` is never elided
(irreversible, environment-dependent). **Caveat:** the plan depends on remote state — bind
the state snapshot's digest into the payload or scope gates to state-independent checks.

## 4. Cross-organization conformance (vendor intake)

**Producer:** a *vendor's* enrolled machine running *your* conformance suite. **Gates:**
API contract tests, schema conformance, security lint — from your published, digest-pinned
suite. **Elided:** your intake re-certification queue; identity = the vendor's enrolled key
in *your* KMS namespace. **Caveat:** this is the highest-adversariality instance (the
producer benefits from lying) — pair with aggressive sampling and short TTLs. The win:
certification lead time drops from queue-weeks to verify-seconds.

## 5. Regulated document workflows

**Producer:** analyst workstation in a clinical/financial reporting chain. **Gates:**
schema and completeness validation, terminology/code-list checks (rule digest = the
regulator's current code lists), cross-field consistency. **Elided:** the submission
portal's synchronous validation pass; the portal keeps auditing asynchronously.
**Caveat:** attestations double as compliance evidence — who validated what, when, under
which rule version — which may be worth more than the compute savings.

## 6. Content and asset pipelines

**Producer:** artist/studio workstation or render node. **Gates:** asset lint (naming,
budgets, texture limits), format validation, license metadata. **Elided:** the asset
ingest farm's validation pass before publish. **Caveat:** binary assets are large — the
tree hash binds them cheaply, but ensure the gate images pin the exact validator codecs.

## 7. Federated fleets (IoT / edge software)

**Producer:** the device itself (identity = device key in org custody). **Gates:**
config/firmware conformance checks run on-device before requesting activation.
**Elided:** the backend's per-device revalidation at check-in scale (millions of devices ×
identical checks). **Caveat:** constrained devices may hold real keys — this instance
benefits most from hardware-backed signers (TPM/TEE), the upgrade path SPEC anticipates.

## 8. Academic benchmarks and competitions

**Producer:** participant machines. **Gates:** the official harness (digest-pinned)
over the official dataset (digest in `tools`), resource-limit checks. **Elided:** the
leaderboard's re-execution of every submission. **Caveat:** adversarial producers by
definition — sampling plus public transparency logs of attestations (countersigning à la
Rekor) is the right posture; PCP turns "trust me" submissions into auditable claims.

---

## The selection test

A gate is a good PCP candidate when all four hold:

1. **Hermetic** — outcome is a function of content + tools + rules, not environment.
   *Architecture-sensitive gates (CUDA, arch-specific builds) still qualify if the producer
   runs equivalent hardware and the payload binds the platform (SPEC §2) — the producer
   need not be a laptop: on-prem GPU rigs and edge nodes are producers too.*
2. **Redundant** — the choke point re-runs what the edge already ran.
3. **Bindable** — content, tools and rules all have stable digests.
4. **Tolerable residual** — a lying *enrolled* producer is bounded acceptably by pinning,
   audit, sampling and revocation (else use TEE signers or don't elide).

If any fails, keep the gate at the choke point. PCP's fail-closed default makes trying it
reversible: remove the skip, and you are back to classic centralized verification.
