#!/usr/bin/env python3
"""
Proof-Carrying Pipelines — reference implementation (v1.0, Apache-2.0).

  pcp.py attest  --repo R [--gates gates.yaml] [--key ed25519.key | --kms KEY_VERSION]
  pcp.py verify  --repo R --attestation A.json [--pub ed25519.pub | --kms KEY_VERSION]
                 [--approved approved.json] [--ttl-hours 24]
  pcp.py keygen  --out ed25519

Dependency-light: stdlib + `cryptography` (Ed25519 backend). The KMS backend shells out to
`gcloud kms asymmetric-sign` / fetched public keys, so no cloud SDK is imported.
This is a clean-room reference: no organization-specific logic.
"""
import argparse, base64, hashlib, json, subprocess, sys, tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ----------------------------------------------------------------- helpers
def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=True,
                          capture_output=True, text=True, **kw).stdout.strip()

def canonical(payload: dict) -> bytes:
    # JCS-style: sorted keys, no whitespace, UTF-8. (Full RFC 8785 for these types.)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode()

def tree_hash(repo: str) -> str:
    # Hash of the *content*: refuse dirty trees.
    if sh(["git", "-C", repo, "status", "--porcelain"]):
        sys.exit("ERROR: working tree is dirty — commit or stash before attesting (P4).")
    return sh(["git", "-C", repo, "rev-parse", "HEAD^{tree}"])

def load_yaml(path):
    try:
        import yaml
        return yaml.safe_load(Path(path).read_text())
    except ImportError:
        sys.exit("ERROR: pyyaml required for gates files (pip install pyyaml)")

# ----------------------------------------------------------------- signing backends
def ed25519_sign(key_path, digest: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    sk = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    assert isinstance(sk, Ed25519PrivateKey)
    return sk.sign(digest)

def ed25519_verify(pub_path, digest: bytes, sig: bytes) -> bool:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization
    pk = serialization.load_pem_public_key(Path(pub_path).read_bytes())
    try:
        pk.verify(sig, digest); return True
    except Exception:
        return False

def kms_sign(key_version, digest: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".bin") as df, \
         tempfile.NamedTemporaryFile(suffix=".sig") as sf:
        Path(df.name).write_bytes(digest)
        sh(["gcloud", "kms", "asymmetric-sign", "--version", key_version,
            "--digest-algorithm", "sha256",
            "--input-file", df.name, "--signature-file", sf.name])
        return Path(sf.name).read_bytes()

# ----------------------------------------------------------------- commands
def cmd_keygen(a):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as s
    sk = Ed25519PrivateKey.generate()
    Path(f"{a.out}.key").write_bytes(sk.private_bytes(
        s.Encoding.PEM, s.PrivateFormat.PKCS8, s.NoEncryption()))
    Path(f"{a.out}.pub").write_bytes(sk.public_key().public_bytes(
        s.Encoding.PEM, s.PublicFormat.SubjectPublicKeyInfo))
    print(f"wrote {a.out}.key / {a.out}.pub  (demo backend — production uses KMS)")

def run_gates(repo: str, gates_cfg: dict):
    """Execute every gate; return (tool_digests, gate_ids). Fails hard on any gate failure."""
    tools, gate_ids = set(), []
    for g in gates_cfg["gates"]:
        gid, cmd = g["id"], g["command"]
        image, digest = g.get("image"), g.get("digest")
        print(f"── gate {gid} " + ("─" * max(1, 40 - len(gid))))
        if image and digest:
            full = f"{image}@{digest}"
            sh(["docker", "run", "--rm", "-v", f"{Path(repo).resolve()}:/w", "-w", "/w",
                "--entrypoint", "sh", full, "-c", cmd])
            tools.add(digest)
        else:  # host execution: pin the interpreter/binary hash instead
            sh(cmd, cwd=repo)
            binpath = sh(f"command -v {cmd.split()[0]}", cwd=repo)
            tools.add("sha256:" + hashlib.sha256(Path(binpath).read_bytes()).hexdigest())
        gate_ids.append(gid)
        print(f"   ✓ {gid}")
    return sorted(tools), gate_ids

def rules_digest(gates_cfg) -> str:
    docs = [Path(p).read_bytes() for p in gates_cfg.get("rule_documents", [])]
    h = hashlib.sha256()
    for d in docs: h.update(hashlib.sha256(d).digest())
    return "sha256:" + h.hexdigest()

def cmd_attest(a):
    gates_cfg = load_yaml(a.gates)
    content = tree_hash(a.repo)
    try:
        tools, gate_ids = run_gates(a.repo, gates_cfg)
    except subprocess.CalledProcessError as e:
        sys.exit(f"GATE FAILED — refusing to sign (spec §3):\n{e.stderr or e.stdout}")
    payload = {
        "pcp": 1, "content": content, "tools": tools,
        "rules": rules_digest(gates_cfg), "gates": gate_ids, "verdict": "PASS",
        "identity": a.identity or sh(["git", "-C", a.repo, "config", "user.email"]),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    digest = hashlib.sha256(canonical(payload)).digest()
    sig = kms_sign(a.kms, digest) if a.kms else ed25519_sign(a.key, digest)
    att = {"payload": payload, "signature": base64.b64encode(sig).decode(),
           "key": a.kms or "ed25519:local-demo"}
    out = Path(a.out); out.write_text(json.dumps(att, indent=2))
    # attach to the commit as a git note (spec §2)
    sh(["git", "-C", a.repo, "notes", "--ref", "pcp", "add", "-f", "-F", str(out), "HEAD"])
    print(f"\nATTESTED → {out}  (also refs/notes/pcp)  content={content[:12]}…")

def cmd_verify(a):
    att = json.loads(Path(a.attestation).read_text())
    p, sig = att["payload"], base64.b64decode(att["signature"])
    digest = hashlib.sha256(canonical(p)).digest()
    approved = json.loads(Path(a.approved).read_text()) if a.approved else {}
    checks = []
    def check(name, ok): checks.append((name, ok)); print(f"  {'✓' if ok else '✗'} {name}")

    print("attest-and-skip gate (spec §4):")
    if a.kms:
        ok = False
        try:
            with tempfile.NamedTemporaryFile(suffix=".pem") as pk:
                sh(["gcloud", "kms", "versions", "get-public-key", a.kms,
                    "--output-file", pk.name])
                ok = _pkey_verify(pk.name, digest, sig)
        except Exception: pass
        check("V1 signature (KMS)", ok)
    else:
        check("V1 signature (Ed25519)", ed25519_verify(a.pub, digest, sig))
    check("V2 identity enrolled",
          not approved.get("identities") or p["identity"] in approved["identities"])
    check("V3 content = delivered tree",
          p["content"] == sh(["git", "-C", a.repo, "rev-parse", "HEAD^{tree}"]))
    check("V4 tools approved",
          not approved.get("tools") or set(p["tools"]) <= set(approved["tools"]))
    check("V4 rules current",
          not approved.get("rules") or p["rules"] == approved["rules"])
    age = datetime.now(timezone.utc) - datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00"))
    check(f"V5 fresh (age {age} ≤ {a.ttl_hours}h)", age <= timedelta(hours=a.ttl_hours))

    if all(ok for _, ok in checks):
        print(f"\nVERDICT: SKIP — gates {p['gates']} proven for {p['content'][:12]}…")
        sys.exit(0)
    print("\nVERDICT: RUN FULL PIPELINE (fail-closed)")
    sys.exit(1)

def _pkey_verify(pub_path, digest, sig):
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    from cryptography.hazmat.primitives import hashes
    pk = load_pem_public_key(Path(pub_path).read_bytes())
    try:
        pk.verify(sig, digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
        return True
    except Exception:
        return False

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
