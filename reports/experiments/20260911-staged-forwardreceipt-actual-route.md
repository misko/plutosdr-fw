# Qualified forward receipt: functional pass, mixed timing result

Branch: `codex/starlink-rx-only-do-not-merge-forward-completion-receipt`.
FW `0e40f84933f942df232da9c01ff9420889579530`;
HDL `48d3dd376693b8c0e3adb9bfb451e01ee7dc58a1`.
**Retain as a tested alternate. Timing still fails; do not deploy.**

## Implemented boundary

The persistent forward-completion token now uses the guard's already-registered,
fully qualified completion pulse. During the extra one-cycle receipt window,
an ACK interlock continues selecting actual product-bank readiness. Delaying
the token without that interlock would permit an early acknowledgment through
kernel-input readiness. The pulse itself never authorizes publication; the
original current/sticky fault veto remains. Raw LAST is not completion proof.

Only the top module changes at runtime. The other 18 compiled runtime modules
are unchanged. Full source inverses constrain both the new change and its
inherited private-ACK/descriptor changes. No added register or clock domain;
native 60 MS/s fine search and 2.5 MS/s inspection are untouched.

## Tests and actual FFT

**545 regression + 14 evidence + seven archive tests pass** (566 distinct tests).
Four unsafe receipt variants are rejected. Complete bench inversion preserves
the prior main campaign, six auxiliary ACK cases and 3,000,000 ns deadlines.
The first focused invocation had a Python import collection error, subsequently
fixed without RTL change; failed and successful XML are preserved separately.

Main real FFT completes in 199.29 s: **64512 indexed numerical records match**.
Service remains **3661/3661/4928/11728/3661/3661 clocks**. The 11728 case includes
an intentional 9000-clock reader stall, excluded from the unchanged 5215-clock
gate. CSV hash changes only through four differently ordered row positions;
an independent comparison confirms identical record multisets and headers.

The original immediate-token witness checks **500638 cycles**, including **98**
one-cycle receipt windows. ACK-wait selection is exact and publication authority
never expands. All inherited numerical, ownership, fault and reset checks pass.

Auxiliary real FFT completes in 77.84 s: **12 new cases** exercise fault, fast
reset, slow reset and healthy continuation before completion, during the receipt,
and after token capture. Every case ends with 512 correct reads and one actual
release. Fault/reset cases show no stale publication or ACK before recovery.
The new witness checks **151827 cycles / 29 receipt windows**. The original six
ACK cases also pass (60721 checks / 306 known-quarantined private differences
at their receipt point), with that monitor active throughout the run.

Routing requires both re-audited, successful, source-matched campaigns. Missing
or altered receipt coverage, or removal of required audit fields, is rejected.
These are finite subsystem tests, not formal or continuous native RX signoff.

## Physical measurement

Synthesis takes 98.39 s; route takes 45.71 s under unchanged constraints.

| Metric | Combined ACK parent | Registered forward receipt |
| --- | ---: | ---: |
| WNS (ns) | -1.421 | -1.567 |
| TNS (ns) | -413.225 | -497.191 |
| Failing setup endpoints | 813 | 681 |
| LUTs | 2763 | 2716 |
| Flip-flops | 5673 | 5665 |

132 fewer failing endpoints, but WNS is 0.146 ns worse and TNS 83.966 ns worse.
Not an overall improvement. All 8261 nets route without errors; hold +0.082 ns
and pulse width +1.830 ns, no failures. Both candidates use 21 DSPs / 15 RAMB18s.
There are still 114 unconstrained inputs and 124 outputs in this diagnostic OOC
build, so it is not full receiver or board timing signoff.

Worst path: **product arithmetic block-start metadata -> product-buffer
identity/framing comparison -> shared fault logic -> forward awaiting-ACK D**.
Nine levels, 7.226 ns data delay, 5.516 ns routing (76.3%). The next worst path
uses the same validation logic to reach kernel-ROM output-valid. The token
dependency changed, but this wide validation feedback remains.

## Next implementation gate

Investigate a product-buffer input validation boundary that holds the word
and its checked identity/framing result together before retirement/publication.
Do not simply delay the fault signal. Require bad final words to remain
unpublished, reset cancellation, 512-word conservation through stalls and
current-fault rejection. Also assess whether redundant per-beat metadata can
be eliminated under proved descriptor/epoch ownership without hiding corruption.
No next-boundary RTL has been implemented in this checkpoint.

Full receiver timing/CDC/reset/board clocks, actual 60 MS/s RX calibration and
sustained Ethernet/IIO qualification remain before reversible `.18` canary and
`.17` PPU Ethernet-only deployment with pinned rollback. Final acceptance still
requires 300-second scans, 120 ms valid dwells and blind host GLRT. No radios,
PPU/main or primary production HDL were changed.

## Preserved evidence

[Read-back verified archive](20260911-staged-forwardreceipt-evidence.tgz) and
[receipt](20260911-staged-forwardreceipt-evidence.json): **13504544 bytes,
5126 members**, all SHA-verified. Archive SHA256:
`bad3215fc8a636d16a242111151f4f53f415f20d14733b081e261c36134bffcd`.

Historical regression fixtures remain an explicit pinned dependency on the
[parent archive](20260911-staged-ackcombined-evidence.tgz), SHA256
`afbc76a605af0b9c16bda45e46cef498eac793b8dbb342023f39d6bccd71fdd9`.
The new packet records its receipt rather than duplicating it; it is not claimed
as a standalone reconstruction of every historical fixture.

- Prepared: `0d222aa4968145b0026ac4e8c9288c9b1ad5fc9f8f9b1bdd07a6d3eda4f1af8b`.
- CSV: `b515f6f4146e28db877474891ed9cebdfa533e8f98bf8c6eb4754afe60bf273d`.
- Synthesis: `ba880cbe1bcabbfc8eb0d6bdf9e16db4119ca13fd34e2aebb4e157fa2082f648`.
- Route: `b353c34642db403990d06908531052c92386c508d78181da4fa273c9dbaa7653`.

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/forward-completion-receipt-worktree-v1`.
RAM-backed artifacts: `/dev/shm/starlink-forward-receipt.7z0zKX` (curated in the
archive above); all tool processes are terminal. Primary production HDL pin
remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
