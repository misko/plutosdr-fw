# L1 saved histories and source-specific OOC preparation

The authorized saved-WDB extraction passed; the physical preparation passed
**58 offline tests /36.05 s**, Ruff PASS. At this preparation gate no simulation
advance, FFT rerun, synthesis or route had been performed.

Tested preparation code: FW `38dfe9d80c33d841d75ebc2ffb46de09eb03b37b` /
HDL `67a1692e3b09f3aa7166fb8f83b1cf787b363f78`. Runtime remains byte-identical to
the tested `62da6a39edb8e40e08d41cbb13ba04af7584842d` L1 source cohort.

## Recorded histories, not selected paths alone

One loader call, original5578 exit0,12:10:31.728129–12:10:39.749783UTC,8.022s.
Directory: `hdl/library/starlink_pss_acquisition/build/local-admission-wdb-history-v1.7RQSIW`.
Exact command: Vivado2022.2 `-mode batch -source <directory>/read_original6473_wdb.tcl
-log <directory>/vivado.log -journal <directory>/vivado.jou`, SuSE environment,
two threads. Script SHA `05d9b02626d2849b4b18bd8c0dfd533d2a102e0fb874a9ffaaeefa9d3a60b7fb`;
original outer-log SHA `2d824c513da39c9f0b44bfe217105dc8d5d19fe50f2cb85b65b27bed27a89f31`.

The original115 arithmetic plus14 observer paths all return recorded values at17
timestamps:2,193 values. Actual/original/default155-bit vectors are equal at all17
snapshots, including identical mixed-X startup values. All345 arithmetic values
at the three previously qualified times match the historical R1B1O1 WDB reference
after only the exact top-scope rename, including the six119-bit comparisons and
deliberately forced external-overflow/current-veto boundary.

| Recorded timestamp | Pre count | Post count |
| --- | ---: | ---: |
| startup0fs | 1 | 0 |
| startup+1ps | 1 | 1 |
| first physical edge | 2 | 1 |
| first edge+1ps | 2 | 2 |
| final edge−1fs | 1,180,131 | 1,180,131 |
| final edge | 1,180,132 | 1,180,131 |
| final edge+1ps / original finish | 1,180,132 | 1,180,131 |

This localizes the outstanding final post counter directly in saved histories.
Physical-time queries do not expose individual same-timestamp Active/Inactive/NBA
iterations; no such ordering is inferred from these samples. Actual6473's full
unconditional assertions and the independent offline scheduling mutations remain
the corresponding execution evidence. Failed14041's precise internal-X cause is
not retroactively established.

WDB SHA `52f4ccf572df859e21cdb6e92a82c3b22459b551874acf241f0ea8acd7539a31` and
all11 owner-inventoried inputs match before/after. A subsequent read-only audit
also verifies all180 original archived actual-run files byte-for-byte, with none
missing. Vivado did add one incidental settings sidecar under
`xsim.dir/tb_starlink_pss_local_admission_actual_behav.wdb/xsimSettings.ini`.
It is preserved separately; the original189-file actual archive is not rewritten.

## Minimal physical preparation, not execution

Bundle: `hdl/library/starlink_pss_acquisition/build/local-admission-ooc-L1R1B1O1-175-prepared-v1`.
External SHA256SUMS identity:
`4ebd909dad1ade64272a33dcc034b9f791270ce1191827266c83ad23ee86703b`.
It contains33 inventoried files:12 physical inputs including8 runtime modules,
exact admission evidence, fixed original recipes, adapted helpers/runner and policy.

Only the selected top/guard names and explicit `LOCAL_FIRST_ADMISSION=1` binding
change the physical design recipe. Its actual RTL default remains0. Complete
inverse checks retain the original arithmetic Tcl359864493a… and original
f843af0394… recipe. The one-shot owner is also an exact inverse apart from helper/
script names and lexical-alias rejection. No arithmetic or functional RTL changes.

Unchanged: xc7z010clg400-1, source100/island175 clock XDC, generated IP factory0795ea7e…,
AreaOptimized_high/OOC, control threshold4, two threads and route0873675f… .
No clock exceptions, input/output-delay changes or open-I/O/CDC waivers.

Admission requires exact actual6473 manifest, all49 inputs, original automation
PASS/zero after-integrity, rerun of its frozen full numerical/fault/metadata/cycle
collector, identical results.json, original WDB hash and the recorded histories.
The original11 functional terminals,155-bit guard checks,76 core jobs, exact
historical CSV and19,456 ordered words/stream remain required;16,986 sample scores
remain oracle-only, not scorer-RTL execution. Generic failure acceptance is absent.

Offline tests cover strict whole-source inverses, L omission/0/X/Z and R/B/O
omissions, copied inputs, rehashed recipe changes, source/parent aliases,
actual-child environment sanitation, recorded-value corruption, late errors,
loader exit0 without completion, exceptions, failed launches, post-failure source
mutation and nonoverwrite. All launch functions are mocks; no Vivado is invoked.
Command: sanitized repository Python `-B -m pytest -q
tests/starlink_oracle/test_local_admission_physical_preparation.py`.

Original75274:57 PASS/1 FAIL/26.90s, retained at
`/tmp/starlink-local-ooc-offline-v1.xrR4mH`. A rehashed frozen baseline-helper copy
was not rejected by direct in-process verification because it used the live fixed
recipe. The only correction adds an explicit frozen reference SHA check.
Original53583:58 PASS/36.05s at `/tmp/starlink-local-ooc-offline-v2.clBlxn`.
Earlier tests, original actual runs and all failed evidence remain preserved.

## Comparison baseline and next gated call

The accepted arithmetic OOC baseline is inventoryc249a13a… . Its synthesized
resources are1,944 LUT/4,547 FF/21 DSP/15 RAMB18; routed resources1,994 LUT/4,557 FF.
Synthesis DCP `de5b7ca6849c8111ccfce29ca39bbf8899276c0dea309abb576e70546daf06bf`.
The existing diagnostic route is **FAIL**:175MHz WNS−1.341ns, global TNS−386.804ns,
497 setup endpoints;100MHz same-domain+2.454ns, cross-domain maxima−0.629/−1.222ns.
Worst endpoint is expected_position→descriptor CE. Hold+0.038ns does not repair
setup failure.114 inputs/124 outputs lack external delays; CDC remains unqualified.

The L1 experiment targets only that descriptor-load control cone. No new area,
slack or clock claim exists. The prepared next call is
`run_local_admission_synthesis.py --execute-synthesis --prepared <absolute bundle>
--expected 4ebd909d… --new-run <new exclusive owner>` and needs separate authority.
No route, D/S/CDC union, canonical promotion, full receiver or RF work is included.

Subsequent source-specific authority allowed exactly one synthesis from this
unchanged bundle, original57050, new owner `local-admission-ooc-L1R1B1O1-175-owned-v1`.
That process was launched after review; its receipts/results are separate from
this immutable preparation archive. Routing remains unapproved at that launch.
