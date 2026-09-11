# Local completion facts: equivalence passes, timing regresses

2026-09-11. DO NOT MERGE firmware/HDL into main. No deployment from this result.
No radio/PPU access. `.14`, `.20` and `.21` remain excluded. Native 60 MS/s fine
search and independent 2.5 MS/s inspection remain required and unchanged.

## Tested change

A separate derived top reduces the private completion snapshot from 42 facts
to 36 and uses the existing private-payload capture option. The six omitted
facts are preflight checks that are inactive in ACK_DRAIN, the only state in
which completion can be requested. The original current public-output vetoes,
quarantine, admission, identity and ownership checks remain intact. All 24
buffered-parent runtime modules are unchanged.

An original 42-fact certificate runs beside the actual candidate as a read-only
reference. Valid facts, permit, validity and consume state match cycle-by-cycle.
Only invalid private payload differs. This is finite tested equivalence, not
formal proof of the full receiver or arbitrary physical corruption.

**1,191 distinct tests pass** (1,165 regression + 26 evidence tests). The six
new component/source/mutation tests are included, not counted twice. Their
unit comparison covers 72,338 sampled edges and rejects four broken variants.

Actual generated FFT main and both auxiliary runs pass. Each checks all 64,512
words from seven numerical streams against the original frozen reference.
Service and numerical CSV remain unchanged: **4,177 clocks / 23.87 us** at
175 MHz, below the 5,215-clock budget. This is not continuous receiver proof.

| Actual run | Original/candidate comparisons | Owned snapshots | Permits |
|---|---:|---:|---:|
| Main | 88,548 | 36 | 36 |
| Auxiliary v1 | 224,178 | 68 | 68 |
| Extended auxiliary v2 | 326,948 | 103 | 101 |

The extended auxiliary run retains six fault injections, eight reset boundaries
and two positive delay cases. It additionally passes ten completion cancellation
cases: faults at snapshot/permit/receipt in both FFT phases, product metadata
and position corruption, and either reset input. Every case rejects cancelled
reuse and recovers with 512 correct fresh words and one reader release.

## Timing gate: failed, do not promote

Same clock/part/Vivado/routing recipe, no timing exceptions:

| Metric | Buffered reference | Local completion |
|---|---:|---:|
| WNS | -1.559 ns | **-1.655 ns** |
| TNS | -348.591 ns | **-504.761 ns** |
| Failing setup endpoints | 742 | **1,163 / 14,131** |
| LUT / FF | 2,735 / 5,800 | 2,719 / 5,787 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

8,427 nets routed without errors. Hold +0.058 ns, pulse +1.830 ns, no hold/pulse
failures. CDC remains nine CDC-3 and 208 CDC-15 warnings; 114 inputs and 124
outputs remain OOC-unqualified. No receiver, CDC or board signoff.

Worst path is output-bank metadata register 20 to output-descriptor pending:
seven LUT levels, 7.245 ns data delay, 79.021% routing. The same current metadata
check reaches multiple failing control endpoints, including inverse commit,
descriptor state, bank publication toggle and sticky fault. The smaller private
snapshot is not a timing fix; retain the buffered parent as the better measured
integrated timing reference.

Next: prototype a buffered/registered inverse-output identity-validation
boundary. Capture the word and identity together, validate locally and wait
for validated final-word/real-bank ownership before publication. Reuse suitable
existing identity-stage patterns. Preserve error fencing at the actual
publication boundary, and test backpressure, late faults, final words, resets,
metadata and real ACK before route. Measure added latency against the existing
service budget. Do not assume an extra stage closes full receiver timing.

## Pinned work and evidence

Branch `codex/starlink-rx-only-do-not-merge-local-completion-facts`:

- FW `ea372e9b31a62cbdc388b1c1735759b85631f56d`.
- HDL `0fc16193701e3e858f92c73dad8958e4b942fd34`.
- Main inventory `32bf941c35383d534bebb2c0d9d0e38c38d2c4d6c9e705d1c344a83f3ccd83cd`.
- Extended auxiliary inventory `0260df5108960e6a5e8ebbee6c0e04e05478ace6637ea2642adedbc4f2f3e07c`.
- Routed DCP `f6a0e7ddc6ce49f74cbe725d3d4b98774a71ee47c4a1e315d6d78ac547f0d095`.
- [Read-back verified archive](20260911-local-completion-facts-evidence.tgz):
  16,104,008 bytes / 6,766 members;
  SHA256 `4382c3ed2bd951d3292ffb86a806f2572646d96d40d0d8fb6ba9bb4d62a3b93f`.
- [Archive receipt](20260911-local-completion-facts-evidence.json).

Includes prepared sources, all actual numerical evidence, generated wrappers,
synthesis/routed checkpoints, raw reports, tests and detailed documentation.
Historical duplicate regression CSV/DCP files remain locally and are hash-listed.
Primary HDL gitlink remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
Deployment remains `.18` canary, then `.17` over Ethernet/PPU, after actual
full-receiver timing, calibration, continuous RX and IIO qualification.
