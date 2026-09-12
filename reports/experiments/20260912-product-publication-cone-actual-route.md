# Publication factoring verified; timing still fails — not promoted

The handoff-specific path improves, but this experiment is **not an aggregate
timing improvement and is not deployed**. Keep the output-retirement parent as
a comparison baseline; do not automatically accumulate this change in the
receiver. Native 60 MS/s fine search and independent 2.5 MS/s IIO inspection
remain required, not removed or replaced.

## Implementation and verification

The candidate adds one derived top, leaving all 39 parent runtime modules
byte-identical. Its only logic change distributes the current ownership enable
over five groups of existing metadata-comparison leaves. There is no added
logical state, latency, delayed certificate, or omitted publication check.

- **1,977 regression tests pass**, plus seven archive-writer tests and two
  recorder tests (1,986 total across the three suites).
- 1,048,576 four-state group/control combinations and 91,680 native metadata
  vectors pass. Every metadata bit, X/Z states and control gates are exercised;
  five unsafe Boolean/slicing mutants are rejected.
- Actual generated FFT main, focused and full auxiliary simulations preserve
  all **64,512 numerical words** and **4,178 service clocks / 23.874 us**.
  CSV SHA: `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
- All **79 actual fault/reset/delay cases pass**: 71 inherited plus eight current
  handoff cases. New cases corrupt five metadata groups, bit 69, position and
  LAST, requiring immediate progress vetoes, stable ownership, quarantine and
  fresh 512-word/one-release recovery. No certificate-only corruption or
  disabled independent oracle is used.
- Independent original-predicate observer: healthy 177,096 comparisons,
  144 enabled checks, no faults; full auxiliary 1,650,464 comparisons,
  3,672 enabled checks, 192 fault-positive checks. Actual full campaign
  elapsed 307.882 s. Focused campaign passed before the full run.

The first archive-recorder attempt rejected Python tuple versus saved JSON list
representations before writing an assessment/archive. Canonical JSON comparison,
with positive and changed-value negative tests, fixes that representation issue.
It does not change or relax the numerical oracle. All actual campaigns passed
on their first run for this candidate.

## Physical evidence

Same Vivado 2022.2, xc7z010clg400-1, 100/175 MHz OOC clocks and route recipe.
No new exceptions, relaxed clocks or physical signoff claim.

| Metric | Output-retirement parent | Factored handoff |
|---|---:|---:|
| Overall WNS / TNS | -1.152 / -343.090 ns | -1.218 / -364.715 ns |
| Failing setup endpoints | 867 / 14,505 | 862 / 14,514 |
| Same-domain 175 MHz WNS | -1.095 ns | -1.022 ns |
| LUT / FF | 2,689 / 5,912 | 2,759 / 5,916 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Source-specific queries run against **both exact routed checkpoints**:

| Path | Parent | Candidate |
|---|---:|---:|
| Product-bank metadata to publication | -1.095 ns | -0.659 ns |
| Engine metadata to product publication | -1.067 ns | -1.015 ns |
| Engine metadata to kernel block-start CE | -0.414 ns | -1.022 ns |

The original handoff path improves by 0.436 ns but still fails. The product
publication endpoint now has its worst path from forward-buffer capture
validation, eight LUT levels, 6.677 ns delay, 78.312% routing. The worst
internal path reaches kernel block-start CE through that same capture-validation
logic: seven LUT levels, 6.447 ns, 79.464% routing. This is a shared control
dependency, not evidence of inadequate FFT arithmetic throughput.

Descriptor CE/data +0.949/+2.604 ns, product occupancy/identity +0.634/+0.438 ns,
output occupancy +0.401 ns remain positive. Output publication is -0.775 ns.
The endpoint query includes all physical request-toggle replicas; this candidate
has one product and one output request-toggle endpoint.

All 8,608 nets route; zero routing errors/loops. Hold +0.070 ns, pulse +1.830 ns.
Nine CDC-3 / 208 CDC-15 / no CDC-10. Scalar fast fault directly feeds its
synchronizer; reset-release and metadata replicas remain unqualified full-board
CDC details. 114 inputs / 124 outputs are unqualified. Overall worst is a held
output descriptor crossing into reader metadata, not a qualified asynchronous
mailbox timing exception.

## Next action and deployment gates

Inspect and prototype separation of capture validation, private replay progress
and checked final publication under explicit registered ownership. The current
forward-buffer `fault` gates replay `output_valid`, which is also used for the
joiner's private-valid input. Any separation must retain current publication
rejection, exact arithmetic/ordering, no stale ownership or reuse, and bounded
reset/fault recovery. Compare against both preserved candidates and require an
aggregate timing/resource benefit; small local slack improvements are insufficient.

Full receiver integration, actual clocks/CDC/reset, routed setup/hold, 60 MS/s
RX calibration, continuous paired RX and actual IIO/Ethernet remain open.
Deploy only via pinned reversible PPU: **.18 first, then Ethernet-only .17**.
No radios, PPU or main branches were modified. **.14/.20/.21 excluded**.
The primary HDL gitlink remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Reproduction and retained evidence

Experimental branch:
`codex/starlink-rx-only-do-not-merge-product-publication-cone`.

- Source FW `d27f92ce0905e64f0b65f82f5d974b1c381c8d68`.
- HDL `c6bcdd7b1e59f93583e3f62d6888144dfeddf19f`.
- Main inventory `40e10861441e6959e9921a6afa4f9099b1797775179562d3c0e2f686ee0b4cdb`.
- Auxiliary inventory `096fdfa1facb088f4d61129e5bc52793f999304731d33899b44491b63368b697`.
- Synthesis DCP `efced2c873e3fd6c79828cd5c332e87c2dbff343951c25e24b2d0270e49f713e`.
- Routed DCP `08da49ead32ddf0ce34310421c35fa77b8019badb9b1bb3cb595beba51e8e4c3`.

[Verified evidence archive](20260912-product-publication-cone-evidence.tgz):
**9,665,309 bytes / 529 members**, SHA256
`d0dda3296255df1bb464f6a7bd6b78573c400458a5e51450bbb52bca267f5995`.
[Sequential verification receipt](20260912-product-publication-cone-evidence.json)
checks every payload hash/size, exact inventory, gzip CRC, stable archive hash
and unchanged sources. Includes prepared designs, actual numeric streams,
generated FFT wrappers, synthesis/routed DCPs, observations, XML results and
focused component artifacts. Historical generated regression payloads remain
local rather than duplicated into the archive.
