# Contributing

PCP is an independent, early-stage project — collaboration is genuinely wanted, not a
formality. The highest-value contributions right now, in order:

1. **Break the threat model.** Read the paper §3/§7 and SPEC, and try to construct an
   attack the predicates and obligations don't bound. Security findings (like the P5
   identity-binding gap, found by an external reviewer and fixed in v1.3) are the most
   valuable issues this repo can receive.
2. **Pilot it.** Wire the attest-and-skip gate into a real pipeline (see `examples/`)
   and report what broke, what was awkward, and what the measured savings were. One
   pilot report is worth more than any number of stars.
3. **Pilot the agent loop.** `docs/agent-loop.md` is a design without empirical
   validation. If you run coding agents against bundle-style pinned gates, we want the
   data — does sensor fidelity + integrity reduce reward hacking and CI failures?
4. **Take a roadmap item.** [`ROADMAP.md`](ROADMAP.md) is prioritized; Merkle
   aggregation for monorepos and the in-toto/DSSE export (O9) are the most impactful
   and are well-scoped. Comment on the issue before starting so we don't collide.

## Ground rules

- **Spec changes** go through an issue first — the SPEC uses RFC 2119 language and
  every MUST/SHOULD has a reason; propose the reason, not just the text.
- **Code** follows the existing hexagonal layout: protocol logic goes in
  `reference/pcp_core/domain.py` (pure — no I/O, no clock, no crypto), effects behind
  ports, adapters in `pcp.py`. Every new predicate or obligation needs a conformance
  test in `reference/tests/` covering its rejection path.
- **Run before you push:** `python3 -m pytest reference/tests/` and
  `reference/demo/run_demo.sh` must both be green.
- **Honesty over polish.** This project earns trust by declaring limits (non-goals,
  validation status, out-of-scope threats). PRs that add claims without evidence will
  be asked to add the disclaimer instead.

## License

Apache-2.0. By contributing you agree your contributions are licensed under the same
terms. Sign commits if you can; use your real identity — fitting, for this repo.
