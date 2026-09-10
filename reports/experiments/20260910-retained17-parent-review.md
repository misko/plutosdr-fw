# Retained old-reader / next-forward prototype: independent first replay

Parent independently compiled and replayed the immutable `retained-composition17-v2`
snapshot. Original handle95674 exited0: **17 PASS in2.50s**, with340 unselected
tests explicitly outside this replay. All42 source/vector/helper hashes passed
before and after. This is scripted-FFT control evidence, not actual FFT, mapped
resources, lower-clock operation, sustained receiver throughput or deployment.

## What was checked

Nine compositions cover three slow-clock phases (0.1/1.3/4.7ns) and three reader
profiles: always ready,13-of-17 ready, and deliberately parked until more than
2200 fast clocks after inverse publication. Each composes the real unchanged
arithmetic and mailboxes with deterministic FFT-port stimulus. Each checks1536
source, forward, product, inverse and final-reader words, including final reader
positions, LAST, descriptor and exponents. Three forward and three inverse jobs
share one scripted FFT and three existing banks. The next forward begins while
the previous inverse remains owned by its reader; the next inverse must wait for
actual reader release. Private retained payload remains stable while stalled.

Eight separate tests cover resetting either side while the slow clock is paused,
at four phases (0.1/1.3/2.9/4.7ns). They exercise actual mailbox state and the
epoch barrier, require stale source contents to be purged, then verify512 fresh
source words. They do not qualify all reset boundaries of the complete receiver.

The parent read the testbench and helper, then added a separate standard-library
saved-log verifier, without importing the implementation owner's verifier. It
checks all42 pins, the17 XML case identities and terminal exits, exact inventories,
all publications, all real ACK timestamps and both next-forward dispatches per
composition. Four altered-log controls (late dispatch, lost word, changed
recurrence, early ACK) are rejected. This supplements the bench: the bench prints
dispatch timing but does not itself assert the8-clock target.

## Measured control schedule and its limits

| Reader profile | Next-forward dispatch after publication | Publication interval | Real ACK after publication |
| --- | ---: | ---: | ---: |
| Always ready | 8 clocks | 3645 clocks | 904–905 clocks |
| 13-of-17 ready | 8 clocks | 3645 clocks | 1177–1185 clocks |
| Parked reader | 8 clocks | 4911–4912 clocks | 3099–3100 clocks |

All nine cases contain1024 next-forward input transfers while old output is
retained. The first two profiles also contain1022 old-reader transfers while a
new forward owns the core. The parked profile correctly contains zero of those
reader transfers: it holds the next inverse until the actual ACK.

Converting cycles to time is a budget calculation, **not** another simulation or
a routed-clock claim. At175MHz,3645 clocks is20.829us and4912 is28.069us, both
below the canonical447/15MS/s =29.8us block interval. At140MHz,3645 is26.036us,
but4912 is35.086us and exceeds that interval. A lower-clock design therefore needs
a concrete downstream stall bound or additional buffering; the earlier nominal
overlap estimate is not a general lower-clock throughput guarantee. The scripted
bench's175MHz-target delay is also quantized by its1ps simulation precision.

## Evidence and next gate

- Frozen source manifest SHA256:
  `c923aa74ad6274b19142e0b1735eacc6e0acf62eb9e42b3aacd0fcbb16060ab9`.
- Parent XML:
  `afdee0eb7b9086b15a26649a71096547dbe550e4268a4d55b318e05e26e62558`.
- Independent `verify.py`:
  `e21b084bf2a5ac6e2a6e14cbb329e690e39e38eccc5f497704e1fc764a4d481d`.
- Parent audit JSON:
  `1f788f571d5f41f081b5be1102fab6e7a17735dad48e03983f33a2a22ec5bcd0`.
- Archive `20260910-retained17-parent.tgz`:907536 bytes, SHA256
  `cfb1d848f3561eb26a577623cbbf63c9aa8386531255e5eab0c4bb4a671e6a5d`;
  tar comparison exited0. Contains all42 frozen files, parent compiled netlists,
  benches, logs, exit receipts, XML and independent audit. Pytest convenience
  symlinks ending`current` are excluded.

Recovery directories are `retained-composition17-v2` and
`retained17-parent.1FJX9vIy` under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Replay the selected cases with `-k 'scripted or fresh_mailbox'`, a new basetemp,
`-p no:cacheprovider`, and the PPU virtualenv Python with PYTHONHOME/PYTHONPATH/
PYTHONOPTIMIZE/LD_LIBRARY_PATH unset. The audit takes RUN_DIRECTORY and
SNAPSHOT_DIRECTORY arguments and creates a new `parent-audit.json` exclusively.

The owner is extending guard/default equivalence, raw-event cutover, watchdog,
long-reader, reset, graph and resource accounting in a different working copy.
Its reported385-case result is **not independently qualified by this17-case
replay**. Freeze and review the complete matrix before any actual FFT run.

In parallel, the product-interface repair is authorized only as additive
primitive/fixture work: separate state-only ACK capacity from exact current-safe
ACK; separate registered-token verdict from raw-offer diagnostics; prevent
bank-valid and qualified-acceptance diagnostics from feeding their own causes.
Preserve immediate independent raw-fault protection and require real guard/product
ordering proofs for any diagnostic-latency change. The first interface remains
structurally FAIL until the repaired full graph and meaningful mutants pass.

No production HDL gitlink, clock, threshold, PPU, radio or main branch changed.
The last physical route remains FAIL; full receiver timing, actual60 calibration,
canonical15 coarse/native fine plus independent2.5 IIO,120ms/300s scanning and
`.18` then Ethernet-only `.17` qualification remain required.
