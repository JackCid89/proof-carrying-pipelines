"""Conformance tests for the pure verifier predicates (SPEC §4) and payload rules
(SPEC §2). Each test names the predicate it exercises; together they are the
executable evidence for the spec's V1-V5 + P5 semantics."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pcp_core import domain
from pcp_core.domain import TrustAnchors

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
TTL = timedelta(hours=24)
KEY = "ed25519:sha256:abc123"

ANCHORS = TrustAnchors(
    identities=frozenset({"dev@example.org", "agent-7@example.org"}),
    tools=frozenset({"sha256:tool-a", "sha256:tool-b"}),
    rules="sha256:rules-v3",
    key_identities={KEY: "dev@example.org", "kms:key-agent": "agent-7@example.org"},
)


def good_payload(**over):
    p = domain.build_payload(
        content="deadbeef" * 5,
        tools=["sha256:tool-a", "sha256:tool-b"],
        rules="sha256:rules-v3",
        gates=["lint", "unit-tests"],
        identity="dev@example.org",
        timestamp=NOW - timedelta(minutes=5),
    )
    p.update(over)
    return p


def run(payload, *, signature_ok=True, key_ref=KEY, anchors=ANCHORS,
        delivered=None, now=NOW, ttl=TTL):
    return domain.verify(payload, signature_ok=signature_ok, key_ref=key_ref,
                         anchors=anchors,
                         delivered_tree=delivered if delivered is not None
                         else payload["content"],
                         now=now, ttl=ttl)


# ----------------------------------------------------------------- happy path
def test_all_predicates_hold_elides():
    assert run(good_payload()).elide


# ----------------------------------------------------------------- V1
def test_v1_invalid_signature_never_elides():
    assert not run(good_payload(), signature_ok=False).elide


# ----------------------------------------------------------------- V2 (+ P5)
def test_v2_unenrolled_identity_rejected():
    assert not run(good_payload(identity="stranger@example.org")).elide


def test_v2_p5_identity_not_bound_to_signing_key_rejected():
    # Enrolled identity, valid signature — but signed with a key belonging to a
    # DIFFERENT enrolled identity. Without P5 binding this impersonation passes;
    # with it, it must fail.
    imposter = good_payload(identity="agent-7@example.org")  # enrolled…
    assert not run(imposter, key_ref=KEY).elide              # …but KEY is dev@'s


def test_v2_unknown_key_ref_rejected_when_binding_configured():
    assert not run(good_payload(), key_ref="kms:unknown-key").elide


def test_v2_without_binding_map_falls_back_to_membership():
    anchors = TrustAnchors(identities=ANCHORS.identities, tools=ANCHORS.tools,
                           rules=ANCHORS.rules, key_identities={})
    assert run(good_payload(), anchors=anchors, key_ref="anything").elide


# ----------------------------------------------------------------- V3
def test_v3_content_mismatch_rejected():
    assert not run(good_payload(), delivered="cafebabe" * 5).elide


# ----------------------------------------------------------------- V4
def test_v4_unapproved_tool_digest_rejected():
    assert not run(good_payload(tools=["sha256:tool-a", "sha256:evil"])).elide


def test_v4_stale_rules_digest_rejected():
    assert not run(good_payload(rules="sha256:rules-v2")).elide


# ----------------------------------------------------------------- V5
def test_v5_expired_ttl_rejected():
    old = good_payload()
    old["timestamp"] = (NOW - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert not run(old).elide


def test_v5_future_timestamp_rejected():
    fut = good_payload()
    fut["timestamp"] = (NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert not run(fut).elide


def test_v5_garbage_timestamp_rejected():
    assert not run(good_payload(timestamp="not-a-date")).elide


# ----------------------------------------------------------------- payload sanity
def test_non_pass_verdict_rejected():
    assert not run(good_payload(verdict="FAIL")).elide


def test_absence_of_proof_never_elides():
    assert not domain.no_proof_verdict().elide


# ----------------------------------------------------------------- canonicalization
def test_canonical_key_order_independent():
    a = {"b": 1, "a": [2, 3]}
    b = {"a": [2, 3], "b": 1}
    assert domain.canonical(a) == domain.canonical(b)


def test_any_payload_field_change_changes_digest():
    base = good_payload()
    d0 = domain.payload_digest(base)
    for field in ("content", "rules", "identity", "timestamp", "verdict"):
        mutated = dict(base)
        mutated[field] = str(mutated[field]) + "x"
        assert domain.payload_digest(mutated) != d0, field
    mutated = dict(base)
    mutated["tools"] = mutated["tools"] + ["sha256:extra"]
    assert domain.payload_digest(mutated) != d0


def test_rules_digest_is_order_sensitive():
    assert (domain.rules_digest([b"r1", b"r2"])
            != domain.rules_digest([b"r2", b"r1"]))
