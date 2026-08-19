#!/usr/bin/env python3
"""
Proof-Carrying Pipelines — reference implementation (v1.3, Apache-2.0).

  pcp.py attest  --repo R [--gates gates.yaml] [--key ed25519.key | --kms KEY_VERSION]
                 [--identity WHO]
  pcp.py verify  --repo R --attestation A.json [--pub ed25519.pub | --kms KEY_VERSION]
                 [--approved approved.json] [--ttl-hours 24]
  pcp.py keygen  --out ed25519

Hexagonal layout: pcp_core/domain.py holds the pure protocol logic (the executable
formalization of spec/SPEC.md), pcp_core/ports.py the boundary Protocols, and this file
is the CLI plus the concrete adapters (git, Ed25519, gcloud KMS shelled out).

P5 note: `--identity` names the enrolled principal the signing key BELONGS to. The
binding is enforced at verify time via approved.json's "keys" map
({key_ref: identity}) — declaring someone else's identity produces an attestation
that fails V2 at every conforming verifier. With per-identity KMS keys, invocation
rights on the key are themselves the identity proof.

Dependency-light: stdlib + `cryptography`. Clean-room: no organization-specific logic.
"""
import argparse, hashlib, json, subprocess, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pcp_core import domain
from pcp_core.domain import TrustAnchors
from pcp_core.service import AttestService, DirtyTreeError, VerifyService

# ----------------------------------------------------------------- helpers
def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=True,
                          capture_output=True, text=True, **kw).stdout.strip()

def load_yaml(path):
    try:
        import yaml
        return yaml.safe_load(Path(path).read_text())
    except ImportError:
        sys.exit("ERROR: pyyaml required for gates files (pip install pyyaml)")

# ----------------------------------------------------------------- adapters: content
class GitContent:
    def __init__(self, repo): self.repo = repo
    def is_clean(self):
        return not sh(["git", "-C", self.repo, "status", "--porcelain"])
    def tree_hash(self):
        return sh(["git", "-C", self.repo, "rev-parse", "HEAD^{tree}"])

# ----------------------------------------------------------------- adapters: gates
class YamlGates:
    def __init__(self, repo, cfg): self.repo, self.cfg = repo, cfg
    def run(self):
        tools, gate_ids = set(), []
        for g in self.cfg["gates"]:
            gid, cmd = g["id"], g["command"]
            image, digest = g.get("image"), g.get("digest")
            print(f"── gate {gid} " + ("─" * max(1, 40 - len(gid))))
            if image and digest:
                sh(["docker", "run", "--rm", "-v",
                    f"{Path(self.repo).resolve()}:/w", "-w", "/w",
                    "--entrypoint", "sh", f"{image}@{digest}", "-c", cmd])
                tools.add(digest)
            else:  # host execution: pin the interpreter/binary hash instead
                sh(cmd, cwd=self.repo)
                binpath = sh(f"command -v {cmd.split()[0]}", cwd=self.repo)
                tools.add("sha256:" + hashlib.sha256(Path(binpath).read_bytes()).hexdigest())
            gate_ids.append(gid)
            print(f"   ✓ {gid}")
        return sorted(tools), gate_ids

# ----------------------------------------------------------------- adapters: signing
def _pub_fingerprint(pub_pem: bytes) -> str:
    return "ed25519:sha256:" + hashlib.sha256(pub_pem).hexdigest()[:32]

class Ed25519Signer:
    """Demo backend. identity = the enrolled principal this key was registered to;
    verifiers enforce the binding through approved.json's keys map."""
    def __init__(self, key_path, identity):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization as s
        self._sk = s.load_pem_private_key(Path(key_path).read_bytes(), password=None)
        assert isinstance(self._sk, Ed25519PrivateKey)
        pub_pem = self._sk.public_key().public_bytes(
            s.Encoding.PEM, s.PublicFormat.SubjectPublicKeyInfo)
        self.key_ref = _pub_fingerprint(pub_pem)
        self.identity = identity
    def sign(self, digest): return self._sk.sign(digest)

class KmsSigner:
    """gcloud KMS backend. key_ref = the key-version resource name. With
    key-per-identity enrollment, invoking this key IS the identity proof."""
    def __init__(self, key_version, identity):
        self.key_ref, self.identity = key_version, identity
    def sign(self, digest):
        with tempfile.NamedTemporaryFile(suffix=".bin") as df, \
             tempfile.NamedTemporaryFile(suffix=".sig") as sf:
            Path(df.name).write_bytes(digest)
            sh(["gcloud", "kms", "asymmetric-sign", "--version", self.key_ref,
                "--digest-algorithm", "sha256",
                "--input-file", df.name, "--signature-file", sf.name])
            return Path(sf.name).read_bytes()

class Ed25519SigVerifier:
    def __init__(self, pub_path):
        self._pem = Path(pub_path).read_bytes()
        self.expected_ref = _pub_fingerprint(self._pem)
    def verify(self, key_ref, digest, sig):
        if key_ref != self.expected_ref:      # signed by some other key entirely
            return False
        from cryptography.hazmat.primitives import serialization
        pk = serialization.load_pem_public_key(self._pem)
        try:
            pk.verify(sig, digest); return True
        except Exception:
            return False

class KmsSigVerifier:
    def __init__(self, key_version): self.expected_ref = key_version
    def verify(self, key_ref, digest, sig):
        if key_ref != self.expected_ref:
            return False
        try:
            with tempfile.NamedTemporaryFile(suffix=".pem") as pk:
                sh(["gcloud", "kms", "versions", "get-public-key", key_ref,
                    "--output-file", pk.name])
                from cryptography.hazmat.primitives.serialization import load_pem_public_key
                from cryptography.hazmat.primitives.asymmetric import ec, utils
                from cryptography.hazmat.primitives import hashes
                k = load_pem_public_key(Path(pk.name).read_bytes())
                k.verify(sig, digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
                return True
        except Exception:
            return False

# ----------------------------------------------------------------- adapters: anchors
class JsonAnchors:
    """O11: in production, fetch these from the org registry / KMS — never from a
    path the changeset under verification can modify."""
    def __init__(self, path):
        self._a = json.loads(Path(path).read_text()) if path else {}
    def load(self):
        return TrustAnchors(
            identities=frozenset(self._a.get("identities", [])),
            tools=frozenset(self._a.get("tools", [])),
            rules=self._a.get("rules"),
            key_identities=dict(self._a.get("keys", {})),
        )

class UtcClock:
    def now(self): return datetime.now(timezone.utc)

# ----------------------------------------------------------------- commands
def cmd_keygen(a):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as s
    sk = Ed25519PrivateKey.generate()
    Path(f"{a.out}.key").write_bytes(sk.private_bytes(
        s.Encoding.PEM, s.PrivateFormat.PKCS8, s.NoEncryption()))
    pub = sk.public_key().public_bytes(s.Encoding.PEM, s.PublicFormat.SubjectPublicKeyInfo)
    Path(f"{a.out}.pub").write_bytes(pub)
    print(f"wrote {a.out}.key / {a.out}.pub  key_ref={_pub_fingerprint(pub)}")
    print("(demo backend — production uses KMS; register key_ref → identity in approved.json)")

def cmd_attest(a):
    gates_cfg = load_yaml(a.gates)
    identity = a.identity or sh(["git", "-C", a.repo, "config", "user.email"])
    signer = KmsSigner(a.kms, identity) if a.kms else Ed25519Signer(a.key, identity)
    rules = domain.rules_digest([Path(p).read_bytes()
                                 for p in gates_cfg.get("rule_documents", [])])
    svc = AttestService(content=GitContent(a.repo),
                        gates=YamlGates(a.repo, gates_cfg),
                        signer=signer, clock=UtcClock())
    try:
        att = svc.attest(rules)
    except DirtyTreeError as e:
        sys.exit(f"ERROR: {e}")
    except subprocess.CalledProcessError as e:
        sys.exit(f"GATE FAILED — refusing to sign (spec §3):\n{e.stderr or e.stdout}")
    out = Path(a.out); out.write_text(json.dumps(att, indent=2))
    sh(["git", "-C", a.repo, "notes", "--ref", "pcp", "add", "-f", "-F", str(out), "HEAD"])
    print(f"\nATTESTED → {out}  (also refs/notes/pcp)  "
          f"content={att['payload']['content'][:12]}…  key={att['key'][:24]}…")

def cmd_verify(a):
    try:
        att = json.loads(Path(a.attestation).read_text())
    except Exception:
        att = None
    sig_verifier = KmsSigVerifier(a.kms) if a.kms else Ed25519SigVerifier(a.pub)
    svc = VerifyService(content=GitContent(a.repo), sig_verifier=sig_verifier,
                        anchors=JsonAnchors(a.approved), clock=UtcClock())
    verdict = svc.verify(att, ttl=timedelta(hours=a.ttl_hours))
    print("attest-and-skip gate (spec §4):")
    if not verdict.checks:
        print("  ∅ no (valid) attestation present")
    for c in verdict.checks:
        print(f"  {'✓' if c.ok else '✗'} {c.name}")
    if verdict.elide:
        p = att["payload"]
        print(f"\nVERDICT: SKIP — gates {p['gates']} proven for {p['content'][:12]}…")
        sys.exit(0)
    print("\nVERDICT: RUN FULL PIPELINE (fail-closed)")
    sys.exit(1)

# ----------------------------------------------------------------- cli
if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="pcp")
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen"); k.add_argument("--out", default="ed25519")
    at = sub.add_parser("attest")
    at.add_argument("--repo", required=True); at.add_argument("--gates", default="gates.yaml")
    at.add_argument("--key"); at.add_argument("--kms"); at.add_argument("--identity")
    at.add_argument("--out", default="attestation.json")
    v = sub.add_parser("verify")
    v.add_argument("--repo", required=True); v.add_argument("--attestation", required=True)
    v.add_argument("--pub"); v.add_argument("--kms"); v.add_argument("--approved")
    v.add_argument("--ttl-hours", type=float, default=24)
    a = ap.parse_args()
    {"keygen": cmd_keygen, "attest": cmd_attest, "verify": cmd_verify}[a.cmd](a)
