# Read-only dependency classification on two complete receivers

The audit now distinguishes a structurally absent combinational dependency
from an untimed connection. It never changes saved constraints or the design.
HDL audit-only commit: `aa1b2d52db4a4fd376ce77786d2201431015a83b`.
Runtime HDL and generated receiver artifacts are unchanged.

For the specifically targeted75 metadata flops to job-start D/CE pins:

- Require the exact source/destination inventory and original5ns clocks.
- If timed paths exist, retain the original strict timing-path report.
- If none exist, trace all combinational arcs, including disabled arcs. Reject
  empty structural fanin or any source still present in that fanin.
- Record proven absence only as `no_combinational_dependency_not_timing_pass`.
  Always separately report the destination's timing from all sources.

This is a saved-netlist combinational observation, not sequential independence,
formal correctness, a clock-domain crossing sign-off or a deployment pass.

## Executed evidence

Both complete Vivado2022.2 audits finished with exit0 at2026-09-10T00:28:01Z.
They rechecked that the input checkpoint hashes were unchanged. Eight new
executed Tcl-policy cases plus existing provenance/constraint/build-policy
tests pass:214 tests total. Ruff passes. Query doubles test omitted/excluded
paths, empty inventories/fanin, query failure and preservation of strict
connected-path checking; the two real DCP runs supply the physical evidence.

| Saved receiver | best18c reference | idle-admission candidate |
| --- | ---: | ---: |
| Metadata to job-start | -.421ns | No combinational connection |
| Job-start from all sources | -.421ns | -1.053ns |
| Input cursor D/CE | +.133ns | -.445ns |
| Input cursor to result fault | -.396ns | -.790ns |
| FFT internal | -.206ns | -.717ns |
| Return slot | +.194ns | -.494ns |
| Output publication | -.118ns | -1.237ns |
| Sticky fault first crossing | +3.691ns | +2.337ns |
| Sticky fault second stage | +4.193ns | +4.193ns |

All tabulated timed paths retain their5ns requirement. The candidate removed
the targeted connection but worsened other paths, including vendor-core
internal paths. It is rejected for deployment, as is the still-failing retained
reference. This is evidence against interpreting a local logic cut as a complete
physical improvement; it does not isolate placement from all other causes.

Candidate final saved-DCP utilization is13060LUT/18575FF/4400slices/53.5BRAM/
54DSP, distinct from its earlier placed-stage report. CDC reports retain9
multi-bit synchronization,199 clock-enable-controlled and7 MUX-hold warnings.
These require protocol-specific review, not blanket acceptance. The13 missing
input/two missing output delays remain; report_cdc skips unconstrained inputs.

## Retained identities

Archive `20260910-routed-dependency-audit.tgz` contains both complete audit
directories and logs, including copied exact audit/RTL sources, per-cone timing,
structural fanin, clocks, exceptions, CDC, utilization, route and check-timing.
No DCP or firmware is included.

- Archive SHA256: `a27941940bbcb6b3af29529847a8f49e388e37c94332f961a827779f728899ba`.
- Exact audit source SHA256: `4dfc1d5a657a451179412064e50a62be2bd84ee8124919690b953ac59c2f52c0`.
- Reference HDL: `18c96bb93f0aea5f868fb8b4c15a2eb1bce7a873`.
- Reference DCP SHA256: `c7939197da381b66600aac228abdd87e20050e71d13903dbcd7abed36cec75b2`.
- Reference summary SHA256: `13a002b5e303143ba23772ecbdfa612648f230d885b323acf56252ca224bac48`.
- Candidate HDL: `d1b3107b56c869d59724df2a8d695112a1f6ac3c`.
- Candidate DCP SHA256: `f7c337695f06dbe95e8659569f4cb7ce9f56c681efb0fc473dc58c70bd121e8e`.
- Candidate summary SHA256: `5c9517e05d7b5e594a7ce3cacc332e590ada8e09b591c29ba334fc8705cdbb09`.

Original evidence lives under `/tmp/starlink-idle-mailbox.N0l1fN/` in
`dependency-best18c-audit-v1/` and `dependency-idle-admission-audit-v1/`.
The previous incomplete audit and its failed-close result remain retained in
the separate failed-route archive; this new observation does not rewrite it.
