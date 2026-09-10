# Paired60 late-command actual v1: overall failure preserved

The one authorized vendor run ended with **exit1**. Its bench completed the
expected late rejection, all coarse/PIL1 checks and final quiet interval, but the
unchanged frozen result verifier rejected the first public audit's labeled-cycle
settle interval. There is no qualified actual PASS, no `terminal_receipt.json`,
no retry and no source/parser/golden/budget change.

## Exact run and integrity

- Original process handle `88460`, initial chunk `74f320`, terminal chunk
  `5a72cf`, exit1. Prelaunch check 2026-09-10 12:24:43 UTC; Vivado exit
  12:25:41 UTC. Launch used the explicitly recorded SuSE LD_LIBRARY_PATH,
  Vivado2022.2 and frozen two-thread runner.
- Tested FW `ba2f8ca59b76a07f0fcbac84371dd2e8a8010056`, HDL
  `813f9eb17c8c1680ef160f202756e25c6a2878b2`.
- Run `/tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-late447-v1`.
  Separate owner directory adds `-owner`; external `.vivado.log` and
  `.vivado.jou` are preserved siblings. `owner.json` records the exact argv and
  original handle/exit, not a reconstructed successful command.
- External and copied bundle SHA
  `b31f0b1612d18ca926eb9698e5beab5c06c4839f49a7cf2da85934e65a46c7f0`.
  All 375 payload files in both copies, all 118 live source hashes and all actual
  simulator-exported memories match. Source signature remains
  `8989b0a7d5353fe657173c64576b8f0b057246e3541750e2c7b890ca4675b997`.
- Generated real FFT wrapper before/after SHA is identical:
  `a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.
- `run_status.txt` says `run_tcl_exit=1 integrity_exit=0`; the original traceback
  is retained. `after_integrity.txt` independently confirms frozen inputs intact.
  Owner `post-audit.json` hashes all 670 raw-run files, 55,780,194 bytes, plus the
  two external logs. Generated project/wave output remains in place unmodified.

## First rejected assertion and read-only interpretation

The exact frozen verifier failure is
`ValueError: late public audit identity/zero-state/deadline` at line88 of
`tests/starlink_oracle/high_rate60_late_result.py` in the frozen inputs. The
first audit begins at control-cycle label 13565; the actual sample handshake was
labeled 13558. Their difference is 7, while the parser requires at least 8.

The frozen bench calls `wait(late_handshakes==1); repeat(8) @(negedge clk);`
before beginning that audit. A sample-domain event occurs between control edges;
its first subsequent control falling edge can retain the event's current
posedge-count label. Eight observed falling edges therefore do not imply an
increase of eight in those integer labels. The preparation's synthetic receipt
used exactly handshake+8 and missed this clock-phase boundary. The second audit,
which starts from source-off rather than this handshake, has a labeled gap of 8.

This is a read-only explanation of the first observed gate failure, not a waiver
or an approved new assertion. The pre-evaluation contract and both original
source snapshots remain unchanged. Any correction must separately specify and
test edge versus elapsed-time semantics, preserve the original failure, and
undergo parent review before execution. A diagnostic pass-through must not be
reported as the frozen gate passing. No later gates were bypassed or relaxed.

## Raw measured receipts (not overall qualification)

| Evidence | Actual observed value |
| --- | --- |
| Public config | rate60, geometry0f8c1108, 264 taps, generation60000001, Eh1073758594 |
| Actual late command | trigger label13505; handshake13558 at raw34359740319; signed lead−64 |
| Identity/classification | request60000520; center/timestamp34359740384; consecutive1, late1, duplicate0, overlap0, last-admitted0 |
| Physical same-edge counters | rejected1, late1, admitted/pending/capture0 |
| First audit | begin13565, generation13613, end13851; generation1, all31 exact words |
| Second audit | begin32423, generation32471, end32709; generation2, all31 exact words; source-off/map-retained1 |
| Native result | no admitted job, capture, raw/qualified tuple, packet read, result or IRQ |
| Source-off | label32415, original16423 plus2 prime, no tail, native capture0/busy0 |
| Negative observation | label32709, 294 controls after source-off; submit/wrapper/FIFO/sample counts1 each |
| Final quiet | labels33102–33358, 256 controls, 154 continuing source rises |
| State checks | 18,395 post-ready sample checks and 30,658 control checks |
| Coarse STOP | selected894/visible894, source9908, canonical2464, pilot319; native0/0 |
| Final conditioned prefix | enabledraw14518; stage30 emitted7251/accepted7250; canonical3618 |
| FFT visible prefix | forward input/output/product/inverse input1536 each; inverse output1024; prepare/ratio/score894 |
| Map | all447 exact words, retained through second negative audit, publicly released after source-off |
| PIL1 | all512 CI16 words; accepted/mixed3617, half1808, all602; exact independent source support |
| Post-rejection real work | 1536 own-FFT-clock forward transfers;2353 pilot accepts; native overlap counters0 |
| Bank quiescence | 20,656 fast-clock cycles; no stale score after bank-local teardown |

The raw capture/tuple/hold files are empty, while the complete original source
trace, separate prime trace, pilot words/bytes, public audit words and all raw
markers remain available. Console/vendor warnings are preserved, not removed.
None of these partial facts changes the final failed-run classification.

The paired geometry remains ideal-clock, static known center, deliberately
expired native scheduling with reduced447x2 coarse integration. It is not causal
acquisition, RF truth, full production-map/750Hz capacity, IIO delivery, deployed
host ABI, physical60 timing or a complete15/30/60 scanner qualification.
