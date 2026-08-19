"""PCP domain — the attest-and-skip protocol as pure, executable logic.

This module is the *formal core* of the reference implementation: every producer
obligation (P-rules) and verifier predicate (V-rules) from SPEC.md that can be expressed
as a pure function lives here, with no I/O, no clock reads, no subprocess calls and no
cryptography — those are ports (see ports.py), injected by the application services.

The intent is that this file can be read side by side with spec/SPEC.md as its
executable formalization, and that the test suite over this module doubles as the
spec's conformance evidence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional, Sequence

PCP_VERSION = 1
VERDICT_PASS = "PASS"


# --------------------------------------------------------------------- canonicalization
def canonical(payload: Mapping) -> bytes:
    """JCS-style canonical JSON (RFC 8785 for the types the payload uses):
    sorted keys, no insignificant whitespace, UTF-8."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode()


def payload_digest(payload: Mapping) -> bytes:
    """SPEC §2: the signature MUST cover the SHA-256 of the canonical payload."""
    return hashlib.sha256(canonical(payload)).digest()


# --------------------------------------------------------------------- value objects
@dataclass(frozen=True)
class TrustAnchors:
    """The verifier's current approved sets (SPEC §1 'sources of truth', §4).

    key_identities implements P5/V2: the mapping from signing-key reference to the
    enrolled identity that key belongs to. When present, an attestation's declared
    identity MUST match the identity bound to the key that produced its signature —
    identity becomes a fact about key custody, not a self-declaration.
    """
    identities: frozenset[str] = frozenset()
    tools: frozenset[str] = frozenset()
    rules: Optional[str] = None
    key_identities: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool


@dataclass(frozen=True)
class Verdict:
    checks: tuple[Check, ...]

    @property
    def elide(self) -> bool:
        """All predicates hold => the verifier MAY elide. Anything else => full
        pipeline (SPEC §4, fail-closed)."""
        return bool(self.checks) and all(c.ok for c in self.checks)


# --------------------------------------------------------------------- P-rules (producer)
def build_payload(*, content: str, tools: Sequence[str], rules: str,
                  gates: Sequence[str], identity: str, timestamp: datetime) -> dict:
    """SPEC §2 payload schema. `identity` MUST come from the Signer port (P5) —
    services enforce that callers cannot substitute an arbitrary string."""
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware (RFC 3339 UTC)")
    return {
        "pcp": PCP_VERSION,
        "content": content,
        "tools": sorted(set(tools)),
        "rules": rules,
        "gates": list(gates),
        "verdict": VERDICT_PASS,
        "identity": identity,
        "timestamp": timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def rules_digest(rule_documents: Sequence[bytes]) -> str:
    """SPEC §2: sha256 over the ordered rule-set documents (hash of per-doc hashes)."""
    h = hashlib.sha256()
    for doc in rule_documents:
        h.update(hashlib.sha256(doc).digest())
    return "sha256:" + h.hexdigest()


# --------------------------------------------------------------------- V-rules (verifier)
def verify(payload: Mapping, *, signature_ok: bool, key_ref: str,
           anchors: TrustAnchors, delivered_tree: str, now: datetime,
           ttl: timedelta) -> Verdict:
    """SPEC §4 — the five predicates, in order, as pure logic.

    `signature_ok` is the outcome of the SignatureVerifier port (V1's cryptographic
    half); everything else is evaluated here. Empty anchor sets skip their check
    (explicitly permissive for the demo; production anchors SHOULD be complete).
    """
    checks: list[Check] = []

    # V1 — signature verifies against a key currently held by the Signer.
    checks.append(Check("V1 signature", signature_ok))

    # V2 — identity enrolled AND bound to the signing key (P5).
    identity = payload.get("identity", "")
    enrolled = (not anchors.identities) or identity in anchors.identities
    if anchors.key_identities:
        bound = anchors.key_identities.get(key_ref) == identity
        checks.append(Check("V2 identity enrolled + bound to signing key", enrolled and bound))
    else:
        checks.append(Check("V2 identity enrolled (no key binding configured)", enrolled))

    # V3 — content equals the tree hash recomputed from the delivered state.
    checks.append(Check("V3 content = delivered tree",
                        payload.get("content") == delivered_tree))

    # V4 — every tool digest approved; rules digest current.
    tools_ok = (not anchors.tools) or set(payload.get("tools", [])) <= anchors.tools
    checks.append(Check("V4 tools approved", tools_ok))
    rules_ok = (anchors.rules is None) or payload.get("rules") == anchors.rules
    checks.append(Check("V4 rules current", rules_ok))

    # V5 — freshness within TTL.
    try:
        ts = datetime.fromisoformat(str(payload.get("timestamp", "")).replace("Z", "+00:00"))
        fresh = timedelta(0) <= (now - ts) <= ttl
    except ValueError:
        fresh = False
    checks.append(Check("V5 fresh (within TTL)", fresh))

    # Verdict field itself must be PASS (SPEC §2: failing runs are never signed).
    checks.append(Check("payload verdict is PASS",
                        payload.get("verdict") == VERDICT_PASS
                        and payload.get("pcp") == PCP_VERSION))

    return Verdict(tuple(checks))


def no_proof_verdict() -> Verdict:
    """SPEC §4: absence of proof is the classic path, never an error — modelled as a
    verdict that never elides (distinct from a failed check list)."""
    return Verdict(tuple())
