# Sampled READY: independent capacity-boundary check

The corrected additive issuer passes the parent's standalone invalid-caller
probe. Removing only its advertised-capacity check makes the same probe fail
at an unauthorized private write. Both actual simulation receipts are retained.
This is a primitive boundary test, not actual P1 reachability, full integration,
vendor FFT, routed timing or radio qualification.

## Executed witness

After normal reset/rearm and one accepted forward admission, the bench offers
an invalid second qualified admission. This naturally creates a one-edge gap:
issuer reason Q is `01`, bank reason Q is zero, internal bank capacity is one,
but externally advertised capacity C is zero. No hierarchical force is used.
An invalid caller then supplies raw VALID=1 and sampled READY A=1.

- Corrected source: current issuer reason7 is asserted, private take stays zero,
  and the following edge retains issuer reasons `81` and bank reason15. The
  simulation exits0 with `PARENT_SAMPLED_READY_CAPACITY_PASS`.
- Deliberate mutant: remove `&& product_ready` only from the opt-in
  `sampled_offer` expression. Private take becomes one despite C=0. The
  simulation exits1 at `PARENT_PRIVATE_WRITE_WITHOUT_ADVERTISED_CAPACITY`.

The mutant's nonzero result is the expected negative control, not successful
receiver operation. This does not replay the historical first defective draft.
The archive directory named `original` contains the corrected source snapshot.

## Exact source and evidence

Issuer SHA256:
`03c37b96aa77562c9f544b0ff4604e944a7b986677703fc546543caa42718f1f`.
Publication bank SHA256:
`76d6985aa2148776ee1e834307066575d269878dc2c32cffd2bdbb87f2c5a490`.
The replay pins and verifies both dependencies as well. Both compilations exit0;
full source copies, bench, commands, VVPs, logs and result JSON are retained.

Archive: `20260910-sampled-ready-parent.tgz`, 112625 bytes, SHA256
`9ce64490026c9958595f28536660fe5ef6bba1b2c95f1eeb222ae340239e856c`.
Archive comparison against recovery files exits0.
Recovery: `sampled-ready-parent.rvnYnNwp` under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

Next gate remains the complete new interface suite, disabled whole-source
equivalence, publication-fault/current-consumer coupling and graph controls,
followed by real controller integration. No production gitlink or radio changed.
