# PCP Architecture — C4 views and the attest-and-skip protocol

This document walks the pattern top-down: **context** (who and what surrounds it), then
**containers** (the moving parts), then the **protocol** (the exchange, step by step).
Diagram sources live in [`../diagrams/`](../diagrams/) as Mermaid; GitHub renders the
copies below natively.

---

## Level 1 — System context

PCP sits between three worlds: identified **producers** (developer workstations, edge
runners) that do the work; the **delivery platform** (repo + pipeline) that must trust the
work; and the **organization's trust anchors** (key custody, identity, approved tooling)
that make the shortcut safe. The pattern's promise: the pipeline's *decision* stays
centralized while its *computation* moves to the edge.

```mermaid
flowchart TB
    dev["👤 Producer<br/>(developer / edge machine)<br/>[Person + identified machine]"]

    pcp["PCP Local Bundle<br/>[Software System]<br/>Runs the pipeline's hermetic gates locally,<br/>binds and signs the verdict"]

    repo["Repository + Delivery Pipeline<br/>[Existing System]<br/>Hosts commits + attestations;<br/>attest-and-skip gate decides:<br/>verify proof OR run full pipeline"]

    trust["Organizational Trust Anchors<br/>[Existing Systems]<br/>KMS/HSM key custody · IAM identity ·<br/>approved tool digests · rule sets ·<br/>audit logs"]

    dev -- "authors change,<br/>runs gates locally" --> pcp
    pcp -- "invokes signing<br/>(never holds keys)" --> trust
    dev -- "push: commit +<br/>attestation" --> repo
    repo -- "verify: signature, identity,<br/>content, digests, freshness" --> trust

    classDef sys fill:#1168bd,stroke:#0b4884,color:#ffffff
    classDef ext fill:#999999,stroke:#6b6b6b,color:#ffffff
    classDef person fill:#08427b,stroke:#052e56,color:#ffffff
    class dev person
    class pcp sys
    class repo,trust ext
```

**Reading:** nothing new is trusted. The producer was already trusted to *write the code*;
PCP extends that identity — under audit, revocation and pinned tooling — to *executing the
checks*, while the verifier keeps the final say.

---

## Level 2 — Containers

```mermaid
flowchart TB
    subgraph producer["Producer machine [identified, untrusted]"]
        direction TB
        gates["Gate Runner<br/>[container executor]<br/>Runs each gate in its pinned image<br/>(digests recorded)"]
        lock["Drift Lock<br/>[versions.lock + check/update]<br/>Pins tool digests + rule-set digest;<br/>refuses to sign when drifted/stale"]
        signer["Signer Client<br/>[CLI]<br/>Canonicalizes payload,<br/>invokes KMS asymmetric-sign"]
        gates --> signer
        lock -.->|"gates run only from<br/>locked sources"| gates
    end

    subgraph anchors["Trust anchors [organization]"]
        direction TB
        kms["KMS / HSM<br/>Keys never leave custody;<br/>every signature audit-logged"]
        registry["Approved Sets<br/>tool digests · rules digest ·<br/>enrolled identities (revocable)"]
    end

    subgraph platform["Delivery platform"]
        direction TB
        git["Repository<br/>commit + attestation<br/>(git note refs/notes/pcp)"]
        gate["Attest-and-Skip Gate<br/>[seconds]<br/>V1 signature · V2 identity ·<br/>V3 content · V4 digests/rules · V5 TTL"]
        skip["Redundant gates<br/>ELIDED ✂"]
        full["Full pipeline<br/>[fail-closed fallback]"]
        rest["Non-elidable stages<br/>(register, deploy,<br/>environment-dependent tests)"]
        git --> gate
        gate -- "proof valid" --> skip --> rest
        gate -. "missing / invalid /<br/>stale / drifted" .-> full --> rest
    end

    signer -- "sign(payload digest)" --> kms
    lock -- "sync check" --> registry
    signer -- "attestation" --> git
    gate -- "verify with public key" --> kms
    gate -- "membership checks" --> registry

    classDef c fill:#438dd5,stroke:#2e6295,color:#ffffff
    classDef hl fill:#e67e22,stroke:#a85a12,color:#ffffff
    classDef ext fill:#999999,stroke:#6b6b6b,color:#ffffff
    classDef sk fill:#f1c40f,stroke:#b7950b,color:#333333
    class gates,signer,full,rest c
    class lock,gate hl
    class kms,registry ext
    class skip sk
```

**Key placements:** the drift lock lives with the producer (it gates *signing*), while the
approved sets live with the organization (they gate *verification*) — drift is therefore
caught on **both** sides, and bumping the approved sets instantly invalidates every
outstanding proof without touching any producer.

---

## The attest-and-skip protocol (sequence)

```mermaid
sequenceDiagram
    autonumber
    actor P as Producer
    participant L as Drift Lock
    participant G as Gate Runner<br/>(pinned images)
    participant K as KMS / HSM<br/>(+ audit log)
    participant R as Repository
    participant V as Attest-and-Skip<br/>Gate
    participant F as Full Pipeline<br/>(fallback)

    P->>L: check lock vs sources of truth
    alt drifted or stale
        L-->>P: refuse to sign (advisory only) → run update
    end
    P->>G: execute gates on clean tree
    G-->>P: PASS + tool digests
    P->>P: canonical payload = {content: tree hash,<br/>tools, rules, gates, identity, timestamp}
    P->>K: asymmetric-sign(sha256(payload)) [IAM-checked]
    K-->>P: signature (operation audit-logged)
    P->>R: push commit + attestation (git note)
    R->>V: delivery event
    V->>V: V1 verify signature · V2 identity enrolled ·<br/>V3 tree hash matches · V4 digests+rules current ·<br/>V5 age ≤ TTL
    alt all checks pass
        V-->>R: SKIP redundant gates ✂ → non-elidable stages proceed
    else any check fails or no proof
        V->>F: run full pipeline (fail-closed — never less safe than classic CI)
    end
```

The verifier is deliberately boring: one signature verification and four set/equality
checks. Its cost bounds the benefit; its simplicity bounds the attack surface.
