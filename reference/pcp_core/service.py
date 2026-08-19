"""PCP application services — orchestration of the domain through ports.

AttestService enforces the producer obligations that involve the world (P2-P5);
VerifyService assembles the facts the pure verifier predicates need (V1-V5) and
stays fail-closed by construction.
"""
from __future__ import annotations

import base64
from datetime import timedelta
from typing import Mapping, Optional

from . import domain
from .ports import Clock, ContentSource, GateRunner, SignatureVerifier, Signer, TrustAnchorSource


class DirtyTreeError(RuntimeError):
    """P4: sign only over a clean working tree."""


class AttestService:
    def __init__(self, *, content: ContentSource, gates: GateRunner,
                 signer: Signer, clock: Clock):
        self._content, self._gates = content, gates
        self._signer, self._clock = signer, clock

    def attest(self, rules: str) -> dict:
        """Run gates and produce the attestation document.

        P4 — refuses dirty trees. P5 — the payload identity is taken from the Signer
        port (the principal the key belongs to); there is deliberately no parameter
        through which a caller could substitute a different identity.
        """
        if not self._content.is_clean():
            raise DirtyTreeError("working tree is dirty — commit or stash before attesting (P4)")
        content = self._content.tree_hash()
        tools, gate_ids = self._gates.run()          # raises on any gate failure
        payload = domain.build_payload(
            content=content, tools=tools, rules=rules, gates=gate_ids,
            identity=self._signer.identity,           # P5
            timestamp=self._clock.now(),
        )
        sig = self._signer.sign(domain.payload_digest(payload))
        return {"payload": payload,
                "signature": base64.b64encode(sig).decode(),
                "key": self._signer.key_ref}


class VerifyService:
    def __init__(self, *, content: ContentSource, sig_verifier: SignatureVerifier,
                 anchors: TrustAnchorSource, clock: Clock):
        self._content, self._sig = content, sig_verifier
        self._anchors, self._clock = anchors, clock

    def verify(self, attestation: Optional[Mapping], *, ttl: timedelta) -> domain.Verdict:
        """SPEC §4. Absence of proof, malformed proof, or any failed predicate all
        converge on a non-eliding verdict — fail-closed, never an exception."""
        if not attestation:
            return domain.no_proof_verdict()
        try:
            payload = attestation["payload"]
            sig = base64.b64decode(attestation["signature"])
            key_ref = str(attestation.get("key", ""))
        except (KeyError, TypeError, ValueError):
            return domain.no_proof_verdict()
        signature_ok = self._sig.verify(key_ref, domain.payload_digest(payload), sig)
        return domain.verify(
            payload,
            signature_ok=signature_ok,
            key_ref=key_ref,
            anchors=self._anchors.load(),
            delivered_tree=self._content.tree_hash(),
            now=self._clock.now(),
            ttl=ttl,
        )
