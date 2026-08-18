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

## 2. ML model promotion

**Producer:** researcher's workstation or training cluster node. **Gates:** eval suites on
pinned benchmark datasets (dataset digests in `tools`), bias/regression thresholds, model
card completeness, license scans. **Elided:** the registry's re-evaluation before promoting
a model to staging. **Caveat:** GPU nondeterminism means gates should assert *thresholds*,
not exact scores; sampled re-evaluation (SPEC O3) matters more here than anywhere.

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
2. **Redundant** — the choke point re-runs what the edge already ran.
3. **Bindable** — content, tools and rules all have stable digests.
4. **Tolerable residual** — a lying *enrolled* producer is bounded acceptably by pinning,
   audit, sampling and revocation (else use TEE signers or don't elide).

If any fails, keep the gate at the choke point. PCP's fail-closed default makes trying it
reversible: remove the skip, and you are back to classic centralized verification.
