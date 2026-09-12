# Current product-publication factoring — DO NOT MERGE

This experiment preserves the actual FFT, buffers, arithmetic, handshakes,
all current publication vetoes, request/ACK ownership, resets and recovery.
Native 60 MS/s fine search and the separate 2.5 MS/s inspection stream remain
release requirements. This isolated subsystem is not the complete receiver.

## Measured parent and bounded change

The output-retirement parent routes with overall WNS -1.152 ns. Its worst
175 MHz internal path is product-bank metadata bit 29 to the bank publication
request, -1.095 ns through eight LUT levels. Read-only checkpoint inspection
identified the actual metadata leaves, handoff reduction, ownership/fault
conditions and downstream publication logic. Synthesized names such as
`awaiting_ack` are net aliases, not evidence that an ACK register is the cause.

The candidate keeps all 39 parent runtime modules byte-identical and adds one
derived top. Its only functional-source edit is Boolean factoring of
`handoff_fault_now`. The existing 24 metadata-comparison leaves feed five
groups of at most five leaves. Each group includes the same current ownership
enable. Their OR, plus the identically enabled position/LAST error, replaces
the previous reduction-then-enable expression. No state or cycle is added.
The original complete identity remains connected to ACK and completion.

The five-leaf-plus-enable arrangement is intended to fit a LUT6 and shorten
the serial logic tree. Physical benefit is a hypothesis until routed under
the unchanged 100/175 MHz OOC recipe; no clocks or exceptions are relaxed.

## Verification and pinned sources

- Exact forward/inverse source transform permits only the top rename and
  predicate factoring.
- 1,048,576 source-derived four-state group/control combinations pass.
- 91,680 source-derived native metadata vectors cover every bit, X/Z,
  control gates and seeded wider patterns. Five deliberately unsafe factoring
  mutants are rejected. These are scoped equivalence checks, not exhaustive
  full-receiver formal verification.
- Actual generated FFT main simulation preserves 64,512 numerical words,
  CSV SHA `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`,
  and 4,178 service clocks. An independent pre/post-edge observer compares
  the original whole-metadata predicate with the new current fault.
- Eight focused actual handoff cases corrupt each comparison group, bit 69,
  position or LAST. They check current progress vetoes, stable ownership,
  quarantine and fresh 512-word/one-release recovery. The full campaign also
  retains the 71 inherited cases. All 79 pass; the full run takes 307.882 s.
  Its independent observer makes 1,650,464 comparisons and sees 192 actual
  fault-positive checks. Healthy main makes 177,096 comparisons, with no faults.
- Main inventory `40e10861441e6959e9921a6afa4f9099b1797775179562d3c0e2f686ee0b4cdb`.
- Focused inventory `85997a61bfe82efbb9abbc37257420e3798881fda393faa2373c3e5af859b013`.
- Full auxiliary inventory `096fdfa1facb088f4d61129e5bc52793f999304731d33899b44491b63368b697`.
- Synthesis DCP `efced2c873e3fd6c79828cd5c332e87c2dbff343951c25e24b2d0270e49f713e`.

Actual routing is admitted only after source-matched main/synthesis/auxiliary
receipts, numerical re-audit and every inherited witness. All physical request
toggle replicas must be measured, not only the original register name.

## Deployment remains gated

The unchanged OOC route completes with zero routing errors but does **not**
close timing: WNS -1.218 ns, TNS -364.715 ns, 862 failing endpoints of 14,514.
The parent was -1.152/-343.090/867. Same-domain 175 MHz worst is -1.022 ns
(parent -1.095). Resources are 2,759 LUT, 5,916 FF, 16 RAMB18 and 21 DSP;
the parent used 2,689 LUT and 5,912 FF. This is not an aggregate improvement.

Read-only source-specific queries on both checkpoints establish:

| Physical path | Parent | Candidate |
|---|---:|---:|
| Product-bank metadata to publication | -1.095 ns | -0.659 ns |
| Engine metadata to product publication | -1.067 ns | -1.015 ns |
| Engine metadata to kernel block-start CE | -0.414 ns | -1.022 ns |

The candidate's critical internal path traverses the forward-buffer capture
comparison/current fault logic into kernel progress. Current `fault` also
gates the buffer replay `output_valid`, which is used for both joiner public
valid and private valid. The read-only observations establish a shared path
to investigate; they do not authorize dropping its same-edge fault check.

All measured descriptor CE/data and product/output occupancy/identity endpoints
remain positive. Output publication is -0.775 ns; product publication -1.015 ns.
There is one physical request toggle for each in this checkpoint. Hold +0.070 ns,
pulse +1.830 ns, zero loops, nine CDC-3 / 208 CDC-15 / no CDC-10. Scalar fault
still directly feeds its synchronizer. Reset-release and metadata replicas,
114 unconstrained inputs and 124 outputs remain part of full-board qualification.
The routed DCP is `08da49ead32ddf0ce34310421c35fa77b8019badb9b1bb3cb595beba51e8e4c3`.

Retain this candidate as a verified non-promoted experiment. The next structural
experiment should separate capture validation, private replay progress and
checked final publication using explicit registered ownership, with proof of
current rejection and quarantine at every transfer boundary. Evaluate it
against the output-retirement parent and this candidate, not merely the newest
checkpoint. Do not keep accumulating LUTs for small local slack changes without
an aggregate timing/resource improvement.

The regression passes 1,977 tests; seven additional sequential archive-writer
tests and two recorder serialization tests pass. The initial recorder attempt
rejected Python tuple versus saved JSON list representations before writing
any assessment/archive; canonical JSON comparison fixes that representation
check while rejecting changed numerical values. The archive writer verifies exact payload hashes and inventory,
gzip CRC, stable archive identity and unchanged sources without random-access
read-back. Full receiver gates below remain open.

No radio access is part of this experiment. The path remains full receiver
integration, actual clock/CDC/reset review, routed setup/hold closure, 60 MS/s
calibration, continuous paired RX and real IIO/Ethernet evidence, then pinned
reversible PPU deployment to `.18` before Ethernet-only `.17`. `.14`, `.20`
and `.21` remain excluded. Do not promote the primary HDL gitlink merely
because this component simulates correctly or an individual path meets timing.
