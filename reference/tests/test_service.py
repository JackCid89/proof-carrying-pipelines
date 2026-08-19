"""Service-level tests with fake ports: producer obligations P4/P5 and the verifier's
fail-closed behavior end to end (no crypto, no git, no containers)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pcp_core import domain
from pcp_core.domain import TrustAnchors
from pcp_core.service import AttestService, DirtyTreeError, VerifyService

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


class FakeContent:
    def __init__(self, tree="feed" * 10, clean=True):
        self._tree, self._clean = tree, clean
    def is_clean(self): return self._clean
    def tree_hash(self): return self._tree


class FakeGates:
    def run(self): return (["sha256:tool-a"], ["lint"])


class FakeSigner:
    identity = "dev@example.org"
    key_ref = "fake:key-1"
    def sign(self, digest): return b"SIG:" + digest[:8]


class FakeSigVerifier:
    """Accepts exactly what FakeSigner produced, for the right digest."""
    def verify(self, key_ref, digest, sig):
        return key_ref == "fake:key-1" and sig == b"SIG:" + digest[:8]


class FakeAnchors:
    def __init__(self, anchors): self._a = anchors
    def load(self): return self._a


class FakeClock:
    def __init__(self, now=NOW): self._now = now
    def now(self): return self._now


ANCHORS = TrustAnchors(identities=frozenset({"dev@example.org"}),
                       tools=frozenset({"sha256:tool-a"}),
                       rules="sha256:rules-v1",
                       key_identities={"fake:key-1": "dev@example.org"})


def make_attestation(**kw):
    svc = AttestService(content=kw.get("content", FakeContent()),
                        gates=FakeGates(), signer=FakeSigner(),
                        clock=FakeClock())
    return svc.attest("sha256:rules-v1")


def make_verifier(content=None, anchors=ANCHORS):
    return VerifyService(content=content or FakeContent(),
                         sig_verifier=FakeSigVerifier(),
                         anchors=FakeAnchors(anchors),
                         clock=FakeClock(NOW + timedelta(minutes=1)))


# ----------------------------------------------------------------- producer
def test_p4_dirty_tree_refuses_to_attest():
    with pytest.raises(DirtyTreeError):
        AttestService(content=FakeContent(clean=False), gates=FakeGates(),
                      signer=FakeSigner(), clock=FakeClock()).attest("r")


def test_p5_identity_comes_from_signer_not_caller():
    att = make_attestation()
    assert att["payload"]["identity"] == FakeSigner.identity
    assert att["key"] == FakeSigner.key_ref


# ----------------------------------------------------------------- round trip
def test_attest_then_verify_elides():
    att = make_attestation()
    assert make_verifier().verify(att, ttl=timedelta(hours=24)).elide


def test_tampered_payload_fails_v1():
    att = make_attestation()
    att["payload"]["gates"] = ["lint", "totally-real-extra-gate"]
    assert not make_verifier().verify(att, ttl=timedelta(hours=24)).elide


def test_content_drift_fails_v3():
    att = make_attestation()
    v = make_verifier(content=FakeContent(tree="0123" * 10))
    assert not v.verify(att, ttl=timedelta(hours=24)).elide


# ----------------------------------------------------------------- fail-closed
def test_no_attestation_is_classic_path_not_error():
    assert not make_verifier().verify(None, ttl=timedelta(hours=24)).elide


def test_malformed_attestation_is_classic_path_not_error():
    for garbage in ({}, {"payload": {}}, {"signature": "xx"},
                    {"payload": {}, "signature": "%%%not-base64%%%"}):
        assert not make_verifier().verify(garbage, ttl=timedelta(hours=24)).elide
