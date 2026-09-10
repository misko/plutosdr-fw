# Checked-product v2: actual FFT PASS; diagnostic route FAIL

Root's fresh actual run **58385 completed exit 0 in 272.65 seconds**. The frozen
original result gate passes, including 32 nominal and six stalled-input real
drains within the unchanged 5215-fast-clock service cap. Source89 and live34
pins remain unchanged; the generated FFT wrapper matches its known identity.
Independent result-CLI verification also returns 0. This is functional actual
FFT qualification, not routed timing, continuous receiver or deployment proof.

## Corrected boundary, not relaxed acceptance

Only the bench adds a bounded live pre-edge drain observation after each of
the two service-profile waits. The original wait calls, stimuli, numerical
comparisons, original result parser and all 14 runtime RTL files remain literal.
The new preparation restores every original84 file byte-for-byte after inverting
the bench addition and the two runner CLI bindings. The original v1 failure is
preserved and has not been reclassified.

The additional drain receipts independently join the actual CSV rows and the
last original-parser service measurement:

| Profile | Jobs | Final forward admission | Live drain | Service |
|---|---:|---:|---:|---:|
| Nominal | 32 | 142157 | 146711 | 4554 clocks |
| Stalled input | 6 | 172014 | 176847 | 4833 clocks |

At cycle146711 the nominal trace now has running=1, WAIT_BANK, forward phase,
result-busy=0 and output-bank-ready=1. Reset begins later. No reset edge is
accepted as successful drain.

Root independently replayed the preparation/scheduler tests: **76 PASS in
0.46 s**, 34 live pins and 89 prepared files unchanged. This includes the
previous 35 scheduler tests, not 76 additional independent runtime tests.
Negative controls reject missing wait, missing readiness/fault fences, omitted
settle interval, service5216, false/missing receipts and altered old acceptance.

## Actual numerical and ownership coverage

The unchanged actual bench reports 44 healthy blocks, 24064 forward words,
24064 product words and 22658 inverse words (44 full blocks plus the deliberate
130-word provisional prefix), with the original purge/fault/reset cases.
The nominal maximum forward interval is4556 clocks. Measured real service spans
4553–4554 nominal and4826–4834 stalled clocks.

Root separately checks all624233 contiguous cycle rows against both observer
counters, and both final live boundaries. The ownership ledger has109367 rows:
74418 private product events,140 publications,131 ACKs and34678 core takes. These
include intentional fault/partial cases and are not a count of healthy frames.
The frozen parser checks complete numerical products, metadata, leases and
publication→ACK→core ordering. Its original 84-case preflight and other fault
and reset coverage requirements remain in force.

Compared with the failed v1 ownership ledger, **every non-cycle tuple is
identical**;1026 event timestamps differ. This diagnostic supports the bounded
testbench change, but does not waive any requirement or turn v1 into a pass.

## Physical gate

Root fully reviewed the minimal source-specific P1 synthesis adaptation and
independently passed **43 preparation tests in0.45 s**,45 source pins unchanged.
The real copier then admits only this original accepted owner, reruns the full
frozen result plus both drain checks and requires exact equality to the owner's
result JSON. Old-v1, missing/false/Boolean drain receipts and changed source
identities are rejected.

The physical preparation selects the exact14 runtime files and all existing
R/D/S/C/K/M/P options plus CHECKED_PRODUCT_BANK=1. The old synthesis owner,
factory, part, clocks and directives are unchanged; the generated synthesis Tcl
is identical to the earlier checked-product preparation draft. Root synthesis
63808 completed exit0 in119.15s:2507LUT5099FF21DSP15RAMB18, zero black boxes.
All25 prepared and45 live source pins remain unchanged. The exact synthesized
checkpoint was then routed by root91981; routing completed but timing FAILS
at -8.324ns. See [the independent physical audit](20260910-checked-product-physical-parent.md).

## Exact evidence

Recovery root:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/`.

- `checked-product-actual-prepared-v2`: frozen89 inventory
  `55288860074df8107d142c97bd69cb67bc71815f13bbb8bacc3b664b9547f5ea`.
- `checked-drain-prep-parent.TQPsrJdl`: independent76 tests/snapshot/XML.
- `checked-drain-actual-parent.wlpL6hYk`: original owner, outcome, logs, source/IP
  checks and independent raw-boundary/ledger `audit.py` and `audit.json`.
- `checked-physical-parent.CJAPlMxt`: independent43 physical-preparation tests.
- `checked-product-physical-prepared-v2`: frozen25 inventory
  `3ad58f680ee32418c3072f896d370604579f593624366c9844c03e7161649177`.
- `checked-synthesis-parent.q1cr3TZZ`: root bounded wrapper around unchanged
  synthesis owner; distinct output, no retries or route inferred from synthesis.

New ownership-ledger SHA256:
`bf12f0013c5e902f3f0866ab3a875dea74646109ec11c48d2a983c401f3bcc13`.
New main-trace SHA256:
`551e9d35d64523b069659e168c395cda395e4b7c13a8c51c28de4cc9ac44bf62`.

No radio/PPU access, firmware-main merge or production gitlink promotion.
