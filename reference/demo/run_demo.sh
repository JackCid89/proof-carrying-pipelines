#!/usr/bin/env bash
# End-to-end PCP demo: keygen → attest (gates run) → verify (skip) → tamper → verify (fallback)
set -euo pipefail
cd "$(dirname "$0")"
PCP=../../pcp.py
rm -rf work && mkdir work && cp -r src gates.yaml work/ && cd work
git init -q . && git add -A && git -c user.email=demo@pcp.dev -c user.name=demo commit -qm "demo"
python3 $PCP keygen --out ../demo-key
echo; echo "══ ATTEST (gates execute locally) ══"
python3 $PCP attest --repo . --gates gates.yaml --key ../demo-key.key --identity demo@pcp.dev --out ../attestation.json
echo; echo "══ VERIFY (expect SKIP) ══"
python3 $PCP verify --repo . --attestation ../attestation.json --pub ../demo-key.pub
echo; echo "══ TAMPER with content, re-verify (expect RUN FULL PIPELINE) ══"
echo "# tampered" >> src/calc.py
git add -A && git -c user.email=evil@pcp.dev -c user.name=evil commit -qm "tamper"
if python3 $PCP verify --repo . --attestation ../attestation.json --pub ../demo-key.pub; then
  echo "UNEXPECTED: tampered content passed"; exit 1
else
  echo "✓ fail-closed fallback engaged"
fi
