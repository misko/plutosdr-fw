# Complete coarse scorer: independent experimental-branch replay

This is simulation evidence, not firmware deployment or physical qualification.
No receiver selection, existing detector arithmetic, radio or PPU source changed.

## Source identity and completed execution

The actual-core runs used primary experimental HDL
`7d85c5af661dad16b1c1561c7a5e7bdb17dc3e61` and firmware `7b677ed2d`.
This merge retains the primary result guard's optional idle-mailbox diagnostic
extension; the bank wrapper leaves its default off. Replaying the actual merged
composition checks this source difference, rather than assuming the alternative
branch's results automatically qualify the merge.

Both Vivado 2022.2 processes terminated with exit 0, at 01:24:07 and 01:25:29 UTC
on 2026-09-10. They use the actual generated FFT, 100 MHz scoring clock and
175 MHz transform simulation clock, with unchanged frozen arithmetic fixtures.

| Test | Executed result |
| --- | --- |
| Numeric and fault/recovery | Four exact epochs, 5,364 scores; initial fixture plus autonomous gap/index recovery and post-reset replay. Five qualifier mutations, direction mutation, core fault and both domain resets pass. |
| Continuous burst/stall capacity | 28,673 source inputs, 64 blocks, 32,768 words at each transform/product boundary, 28,608 ordered scores; every block's metadata reconciled. |
| Capacity bounds | FIFO maximum 358/512, scheduler queue maximum 1, ring age 589, energy lookup age 847/2048, score age 914; no ingress stall. |

The observed forward admission intervals of 5,198–5,232 fast clocks are
arrival-paced, not a saturated engine speed measurement. Strict next-epoch
capture during RUN_JOB and three-epoch overlap witnesses are both zero in this
continuous-source bench; do not claim those overlaps from this test. The separate
saturated bank study tests overlap. Capacity count/order checks are not a
numerical oracle and the numeric replay is not RF detection evidence.

## Reproducibility and limits

Archive `20260910-bank-composition-primary-replay.tgz` contains the two full
runner logs, simulator logs, scopes, frozen inputs and generated testbenches.
It excludes vendor-generated IP and deployment binaries. Recreate the actual
FFT with the included pinned creation script and Vivado 2022.2.

- Archive SHA-256: `1b4cd87a10d940f7d2a644445272f61bcefefe76c0a56b8a186974b855b7ec9d`.
- Numeric runner log: `0df7e73549d83cf99bfd8ad3538d4256e543ca4533d57a928f8b0ad0b7034cb6`.
- Capacity runner log: `8153f2d5f2d3344b0f584bbe4f2d40525af5d745b49686bc4a585418a9df18cb`.
- Tested result guard: `116aab63f3f0c74e590ee384d5afb7ae996dbf863554afb5a4d17684b498ba1d`.

Subsequent evidence-only merges produce HDL
`39bbf8a131e1b83e70e3875c697c12f11f23b03c` and firmware
`9279a7459dfc9ceeb82b2797ece4ea954786a73a`; they add the synthesis runner and
collector/report hardening, not runtime RTL. The primary rerun of runner policy,
composition evidence and resource parser tests passes 61 tests.

The alternative's full composition synthesis independently reports 3,868 LUTs,
6,499 FFs, 27 DSPs and 14 BRAM tiles, with no black boxes. See
`../starlink-bank-owned-iq-to-score-resources-20260910.json` for source-specific
hashes and complete hierarchy. Do not infer routed receiver savings by
subtracting different isolated and full-design inventories.

Still required: long capacity soak, successful internal and full receiver
routing/timing, explicit clock/CDC/reset integration, native fine plus pilot
integration, source-rate calibration, .18 qualification and Ethernet/PPU .17
verification. The current failed physical results remain counterevidence.
