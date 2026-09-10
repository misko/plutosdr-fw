# Local first-admission L1/R1B1O1/175 — actual-core PASS

The one authorized prepared-v4 run passed, original handle6473 / process exit0.
Start2026-09-10T11:57:51.596981UTC, end12:01:46.110204UTC,234.513s.
Runner run_status0/after_status0, launch_error=null, after_integrity_error=null,
results.json present. All49 frozen files and manifest match before/after; generated
vendor IP pre/post/live source is unchanged. No retry, L0 run or physical run.

Source FW `8130a750734c6fd9fc8cedb4131cfa9e56b71d22` /
HDL `62da6a39edb8e40e08d41cbb13ba04af7584842d`; preparation evidence was committed
as FW `9d1bb7c73` before launch. Frozen L1-v4 manifest:
`1717107b5be08b9ff72e7a224cbf20a1354ddd215270a7cd1923b62e12b5d858`.
The runner remains `f76090eba45113c44eff258fa1482198b663747787b76b14ce24a39bee7ebb98`.

Owner: `hdl/library/starlink_pss_acquisition/build/local-admission-L1-175-actual-owned-v3`.
The new owner script SHA is
`b43b41f1bb94432ae1c82c0d8a1520a2d0e1f2e446d71ec1f9a27b7867e284f1`:
exactly the four authorized substitutions from owner-v2 (new prepared/owner paths,
manifest and46→49 count). Vivado2022.2 SuSE environment, two threads, clocks,
generics, IP factory, stimulus, vectors and all original assertions are unchanged.

## Completed evidence

All11 original functional terminal contracts and the new155-bit guard terminal
pass. The unchanged frozen postprocessor was also rerun read-only from `/` after
process completion; its JSON is byte-identical to the original results.json.

- 32 nominal and6 stalled numerical blocks;19,456 ordered words in each forward,
  product and inverse stream. All16,986 output-derived exact sample scores match;
  these are **oracle-only, not scorer-RTL execution**.
- Event CSV SHA `7bbe79fd2648984f0901296d69c1e168cac400426eb2642e91e24ff3815803f3`.
- Complete historical R1B1O1 CSV SHA
  `e7127798f315772b95aff63b75fffcd9cf5d1af8ca3c96e878bae4b39e443d71`.
  No trace retiming, omitted event fields or modified expected values.
- All76 nominal/stalled core-job records retain config_delta3, input_span513,
  input-last→first-output781, admission→commit1810 cycles. Product accepted-token
  to bank latency remains4 clocks. Observed nominal maximum forward interval4549
  cycles is unchanged; it is not a universal stall bound or physical clock proof.
- Original fault/reset suites remain:10 primary fault cases,4 purges,130 accepted
  provisional-prefix words under late-fault quarantine, plus the complete raw-ready,
  preflight, boundary, active-input and reset suites recorded in results.json.

The new observer compares the literal original and actual omitted-default guard
against L1 on every clock/reset event, without valid/epoch/fault/reset masks:
pre1,180,132; post1,180,131; reset256; forward starts150; inverse starts71;
current faults17; sticky faults897; completed checks320,098; closed prefetch13,859;
duplicate checks2. All155 state/output bits and current/certificate predicates
remain in the comparison. Added hardware latency is0.

The pre/post counts are explicitly unequal by one; they are not rewritten.
The raw finish timestamp3,371,803,026,733fs equals
1,180,131×2,857,143fs (the quantized fast half-period) +1,000fs.
Thus termination shares the final edge's +1ps post-check time slot. The original
final sequence calls unconditional compare(4), then arithmetic receipt and $finish.
This supports a final same-slot counter-ordering explanation; no extra edge was
run and no pending-check count was invented. The offline model independently
checks every completed event before its final receipt.

## Preserved scope and waveform status

The saved WDB is130MiB, SHA
`52f4ccf572df859e21cdb6e92a82c3b22459b551874acf241f0ea8acd7539a31`.
Both exclusive diagnostic receipts and115 arithmetic plus14 observer paths exist
at the exact escaped parameterized root. **Recorded history extraction is pending**
at this report's initial archive gate; selecting paths is not itself a proof of
their recorded values. No waveform loader was invoked in the run/collector phase.

Original simulate.log SHA
`ead881d85bbcc6325e6300b8b26ef62ada0db4defce9ae91962db726c1f85e74`;
outer.log SHA `3831f99e5cb1a581f9c34cd33c8e3b34ec805ba1dfee6fed84e7cef7f888a344`.
The complete original project, WDB, logs, commands, original exit and source/IP
before/after receipts are archived without rewriting them.

The successful run qualifies this **settled pre-NBA observation schedule** in the
actual-core context. It does not retroactively identify the exact internal-X cause
of failed14041. Failed22656, failed14041 and every offline failed control remain
separately preserved. Existing arithmetic historical automation failures retain
their distinct post-hoc qualification history.

No D/S/CDC union, canonical-runtime promotion, physical timing, complete receiver,
RF or detection-accuracy claim follows. Continuous canonical15 coarse from original
15/30/60, sparse native fine, independent2.5MS/s pilot and full dwell requirements
remain the larger objective, not replaced by this bounded input-guard test.
