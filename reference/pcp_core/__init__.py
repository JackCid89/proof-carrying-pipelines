"""PCP core - executable formalization of spec/SPEC.md (pure domain + ports + services)."""
from .domain import (TrustAnchors, Verdict, Check, canonical, payload_digest,
                     build_payload, rules_digest, verify, no_proof_verdict)
