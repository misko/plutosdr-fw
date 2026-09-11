# Local fault pipeline rejected before routing

**New functional boundary test fails. No timing improvement or deployment claim.**
No radios, PPU/main or primary HDL pointer were changed.

The new derived top independently captures 33 fault facts before reduction,
then retains the scalar global fault register as the direct CDC source. This
delays newly detected global faults one clock while retaining immediate
already-latched guard faults and existing public gates. All 27 parent runtime
modules are unchanged. That delay requires independent publication containment.

## Evidence and rejection

Final unit/regression run: **1,306 pass**, including 27 new transform/witness
cases and 38 extracted-register RTL cases. The healthy actual FFT run matches
64,512 reference words and retains 4,178 service clocks in all six contexts.
Synthesis passed. Those results do not establish fault safety or real-time RX.

The auxiliary actual run passes 31 earlier fault/reset/delay boundaries and
new boundary 0, then fails new boundary 1: unexpected FFT status on the final
product-write edge does not immediately veto product publication. New cases
2–5 were not reached. **No route was launched after that failure.**

A separate parser defect initially rejected a valid healthy marker and caused
two regression failures. Original source/receipts and failed regression remain
retained. The v3 re-auditor corrects parsing, verifies frozen source/logs and
numerics and writes a separate healthy receipt; it does not accept the failed
auxiliary run. Re-auditing is not another simulation.

## Parent/candidate actual-FFT reproduction

Both separately pinned diagnostics inject status VALID / `8'h80` at actual
product position 511, with the reader held:

| Observation | Parent | Candidate |
|---|---:|---:|
| Current combined fault | 1 | 1 |
| Current external / vendor fault | 0 / 0 | 0 / 0 |
| Product permission / RAM accept | 1 / 1 | 1 / 1 |
| Product ownership request after edge | **0 → 1** | **0 → 1** |
| Global / guard fault after edge | 1 / 1 | 0 / 1 |
| Settled fault / host reads / reader releases | 1 / 0 / 0 | 1 / 0 / 0 |

This is an **inherited internal-publication gap**, not evidence of a new host
data leak. Both quarantine without host output in these probes. The stronger
test exposes that product publication checks current external faults and
latched guard faults, but not current guard-local faults. Current FFT status
is not part of the top-level `vendor_fault_now` predicate.

Next add the current guard-local veto to actual product publication. Check
READY/framing feedback and unknown authority; extend actual final-write tests
to unexpected status, raw output, frame/input events, completions and reset.
Only route after complete healthy and cancellation campaigns pass. Keep all
failed evidence; do not weaken the publication contract to obtain a pass.

## Pinned branch and retained evidence

Branch `codex/starlink-rx-only-do-not-merge-local-fault-pipeline`:

- FW `45c01efb99d7dbb7e9c938901bbb40ddd28f49a9`.
- HDL `da38d32b1f007b2e9eac2419b9cc6b6377977bcc`.
- Main source inventory `55f381e1950ed92a36f0af44d07d5e087d6b3d467597524e13004ccb71c7c394`.
- Auxiliary inventory `faa4b4a29a3a1261f691351652ce3c1fa5a61784c0ac2b32c90eb7b621b8985c`.
- Synthesized DCP `ef080ea555fcf21abf6cffb1ef0fac6a61249d42a9aacbf1cff5661734bce92d`.
- Parent diagnostic inventory `78b7c743caeae67646b61b82ed7ab85ec3814839941f1bf5a6f1f45ca728f985`.
- Candidate diagnostic inventory `7ba74fe41d342d19ba81b641153b8de9974ac373d232a505559006371ec5c627`.
- [Read-back verified archive](20260911-local-fault-pipeline-rejection-evidence.tgz):
  19,167,719 bytes / 15,617 members; SHA256
  `e59d57e826c21e6e0147064da50e8cfecec857b5da804e9029da48a09d912863`.
- [Archive receipt](20260911-local-fault-pipeline-rejection-evidence.json).

Archive retains all four prepared campaigns, healthy/failed actual logs and
streams, both diagnostic reproductions, generated FFT wrappers, synthesized
checkpoint, passing/failing regressions and source. Historical regression
CSV/DCP duplicates remain local with a hash inventory.

Primary HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
Native 60 MS/s fine and independent 2.5 MS/s inspection stay required. Full
receiver timing/CDC/reset, calibration, continuous RX and IIO/Ethernet remain
open before reversible `.18` canary, then `.17` Ethernet/PPU deployment.
`.14`, `.20`, `.21` remain excluded.
