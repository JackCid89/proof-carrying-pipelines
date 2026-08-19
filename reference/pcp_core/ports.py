"""PCP ports — the boundary between the pure domain and the world.

Hexagonal layout: the domain (domain.py) never touches these directly; application
services (service.py) orchestrate domain logic through these Protocols, and the CLI
wires concrete adapters (git, Ed25519, gcloud KMS) at the edge (pcp.py).
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

from .domain import TrustAnchors


class Signer(Protocol):
    """The organization-held signing capability (SPEC §1 'Signer').

    P5: `identity` is a property of the signer — the enrolled principal the signing
    key belongs to — never a caller-supplied string. `key_ref` is the stable
    reference verifiers use to re-derive that binding (KMS key-version resource
    name, or a public-key fingerprint for the Ed25519 demo backend).
    """
    @property
    def identity(self) -> str: ...
    @property
    def key_ref(self) -> str: ...
    def sign(self, digest: bytes) -> bytes: ...


class SignatureVerifier(Protocol):
    """V1's cryptographic half: verify `sig` over `digest` for `key_ref`."""
    def verify(self, key_ref: str, digest: bytes, sig: bytes) -> bool: ...


class ContentSource(Protocol):
    """The delivered state (a git repository, in practice)."""
    def is_clean(self) -> bool: ...
    def tree_hash(self) -> str: ...


class GateRunner(Protocol):
    """Executes the gate set from locked sources; returns (tool_digests, gate_ids).
    MUST raise on any gate failure — failing runs are never signed (SPEC §2)."""
    def run(self) -> tuple[Sequence[str], Sequence[str]]: ...


class TrustAnchorSource(Protocol):
    """Where the verifier's approved sets come from. NOTE (O11): this source MUST NOT
    be modifiable by the changeset under verification — fetch from the org registry /
    KMS, or from repo paths protected separately from producer code."""
    def load(self) -> TrustAnchors: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
