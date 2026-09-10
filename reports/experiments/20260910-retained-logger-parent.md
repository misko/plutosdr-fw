# Logger correction verified; actual frame assumption is not the vendor contract

## Independent preparation gate

Parent69282 exits0:180 PASS in22.86s, all77 source hashes unchanged. Delta
against v3: six changed sources, four additive sources,67 unchanged sources.
Receiver runtime, FFT factory, numerical vectors, clocks and existing detailed
guard bodies remain byte-identical. Only two conditional-string formatter
calls become explicit if/else literal calls; the checker additionally rejects
the previously missed FATAL_ERROR token.

The two-site inverse restores both the entire old witness and the expanded
v3 bench hash. Fresh full scripted runs of old and corrected benches produce
identical77953-row CSVs, SHA256
`07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa`.
All receipts match except one expected Icarus $finish source-provenance line:
the independently derived unique $finish line moves506→508 with the two added
source lines; simulation time512702882778fs is unchanged. The owner's original
179PASS/1FAIL attempt remains recorded: its overstrong raw log-byte comparison
failed on that provenance alone. No general log normalization was introduced.

The parent also independently joins the frozen bundle to77 tested source pins,
checks180 clean XML cases, reconstructs the entire original bench with its own
two-site inverse, and verifies unchanged profile/vectors/compiled list before
the vendor call. The original kernel-marker acceptance counterexample remains
preserved; new exact-message/mixed-case regressions now reject it.

Frozen FW `d49ceb8b0f84f8ab3d4ec8233587dd9c81065b3e`;
HDL `b94909a6c15a2b99cd5cd0bcdc6d646d2a05c575`.
Manifest SHA256 `eef29e37ca54241a3fc8cc664b07bfdb4b8948b72be4207e6a44953f7d9cbc38`.

## Actual result: previous crash removed, new assertion failure

Parent25461 exits1 after28.89s, without timeout. Both source-copy checks exit0,
no results.json exists, and the strict checker rejects the fatal assertion.
The run passes repaired startup, admits job1 at934, and writes512 complete
source rows plus three complete physical input rows. There is no logger kernel
crash in this run. The next stop is:

```
Fatal: actual fresh frame ordinal
Time: 5380000269 fs
```

Physical input positions0,1,2 are accepted at fast cycles939,941,942. The
testbench event check at942 requires its post-handshake input counter to equal1,
but that counter has reached3. This assumption was inherited from the scripted
FFT actor, which emits its frame pulse on the first input handshake. It is
not the documented vendor-interface meaning.

AMD defines event_frame_started as a one-cycle indication of starting internal
frame processing, useful for frame counting/configuration. That definition
does not equate it to the first external AXI input handshake or establish a
universal three-cycle delay. [PG109 v9.1, May4 2022, p12](https://www.amd.com/content/dam/xilinx/support/documents/ip_documentation/xfft/v9_1/pg109-xfft.pdf)

Prior passing L1 actual benches counted one frame by commit, not equality to
input ordinal1. Their retained CSVs contain no direct frame-event column, so
they do not independently establish a universal +3 event bound either.

## Approved correction direction, not yet qualified

Replace the script-specific equality with an explicit causal per-job frame
contract: fresh admitted/configured reset epoch; at least one accepted physical
input; one single-cycle frame pulse; no previous frame/raw result; frame before
first raw output; no stale/duplicate/unowned events. Add frame-cycle and accepted
input before/on/after evidence and join it independently to input/output/job/
reset records, including aborted jobs. Test malformed early, duplicate, late,
stale and counter-inconsistent records. Record measured delays without fitting
a universal expected3 to this single observed job.

Retain all exact configuration/input-span/status/raw-output/service bounds,
numeric comparisons, production guards and prior failures. A new source-bound
bundle and fresh actual run are required. This is a correction to an erroneous
testbench assumption, not proof of numerical, timing or deployment completion.

## Evidence

- `20260910-retained-logger-parent.tgz`, SHA256
  `d94baf89d054ff9175dabe05c84927472837c7e5c51473aa0f15a87da180b510`:
  independent180 source/case/log/CSV/XML and before/after pin evidence.
- `20260910-retained-logger-actual-parent.tgz`, SHA256
  `2f48bb05654f9eb21c0ff0a77258b319827f09b8095c1a688c12458455e87a30`:
  complete owned actual attempt, source copies/project/IP, logs, partial CSV,
  source audit and terminal receipts.

Both archive comparisons exit0. Python bytecode, convenience current links and
tool `.Xil` scratch are excluded where applicable. Recovery directories
`retained-logger-parent.AzSFiJw2` and `retained-actual-logger-parent.JScn6pzV`
under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
No radio, PPU, production HDL gitlink, synthesis or route operation occurred.
