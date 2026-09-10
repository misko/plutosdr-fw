# Additive bank arithmetic: offline port and ownership qualification

This bounded study passes **101 offline tests in 14.29 s** (65 new, 36 unchanged
regressions). It does not run a generated FFT, synthesis, placement, routing, a
receiver, or hardware. Original bank/core/control/legacy-bench bytes are unchanged.

## Source boundary

Independent FW/HDL worktrees are under
`/tmp/starlink-coarse-alternatives.Y3JzOI/bank-arithmetic`, on
`codex/starlink-rx-only-do-not-merge-bank-arithmetic`. Exact bases are FW
`bda25bb5e0a5e98b7a3c1f4921618d040f709bfa` and HDL
`dec20d6371f2d77b6e09c4bcdda2f3d7f8715776`; the initial FW gitlink matched.
The separate operand-boundary physical tree/evidence was not changed.
The tested additive HDL is committed as
`41e539e768fde9f36dcb67aeedc7971de6e84d73`; this report's FW commit pins it.

Six HDL files and one FW policy file are additive. The new arithmetic core is
strictly invertible to the entire dec20 product, including its sequential
`PRIVATE_PAYLOAD_BUBBLES` behavior. Only module identity, a default-zero rounding
option, and the exact previously reviewed rounding blocks from
`f7345ab655a21374f46d2bda89854f40295fca24` differ. The original core SHA256 remains
`f4fd79f2744cbaf4d7caa6afdf2781ab588fff612266cdb377593bbb31076669`.

The distinct `starlink_pss_fft_bank_owned_arithmetic_probe` is strictly invertible
to dec20's bank: rename, two default-zero parameters, and its product-instance
binding are the only differences. `PRIVATE_PAYLOAD_BUBBLES(REGISTERED_SCHEDULING)`
is retained. Tests verify the actual probe → operand wrapper → new core hierarchy
and forwarded values; existing runtime/default bindings are not promoted.

## Token, latency and fault contract

`REGISTER_OPERANDS=0` is direct passthrough. Option 1 adds one elastic stage for
both complex operands and all 79 metadata bits, plus one validity bit: logical
state `4*DATA_WIDTH+80`, or **152 bits at width 18**, and one extra token capacity.
Measured no-stall acceptance-to-output elapsed clocks are 2 versus 3. This is not
a shifted whole-chain equivalence claim: stalls change absolute event timing.

Reset/flush empties the stage; simultaneous dequeue/refill is supported. Occupied
stalled payload cannot change. With private bubbles enabled, only an available
slot's numeric fields may update on an invalid input; metadata and token ownership
remain protected. ROUND/REGISTER/PRIVATE reject −1, 2, X and Z in directed tests.

Overflow remains an insertion-time pulse in the core and a held output flag while
stalled. The bank continues using the **held flag**, not the pulse, in both current
fault predicates and its original sticky/publication gates. Directed tests hold
real saturation at nonfinal and final product tokens: insertion is observed,
then the pulse clears while the held cause and quarantine persist. A no-clock
predicate-only snapshot temporarily masks already-latched `fast_fault` to prove
the held cause independently; this is not a natural hardware rollback experiment.

## Executed checks

- Independent integer complex math, ties-even rounding, saturation, metadata,
  occupancy, exact default public-bit behavior, bounded stalls, simultaneous
  refill, X/Z invalid bubbles, saturating-last reset/flush, and final drain. Twelve
  width/round/private runs each exercise both register modes: all eight flag
  combinations at widths 2, 18 and 24, with 1,024 vectors and 5,010 cycles/run.
- Eight bank flag combinations each retire two ordered zero frames (1,024 words),
  with positive N+1 prefetch protection and final-product ownership-delay witnesses.
- Eleven bank boundary cases in each register mode: nonfinal/final saturation;
  late forward faults before and after product-bank ownership; malformed final
  start/exponent/TLAST/position; late inverse fault after an accepted slow prefix;
  fast reset during the forward tail; and withheld final status. Each then proves
  fresh common-epoch recovery with 512 ordered words. Prefix quarantine observes
  20 → 22 provisional words during an eight-slow-clock CDC wait, no complete block;
  status withholding keeps the final product unpublished for 12 fast edges.
- Eight faulty operand/publication mutations and twelve invalid parameter cases
  must terminate with their specific failure, not a permissive PASS. An unchanged
  full old-guard shadow checks the candidate environment every edge.

The bank bench uses an explicitly labeled synthetic zero-frame interface with
`OFFLINE_NOT_FFT=1`, not vendor FFT arithmetic/timing. It drives the real guards,
joiner, product, mailboxes and CDC/reset/ACK lifecycle at artificial cadence. The
100/175 MHz simulation clocks and zero-frame results imply **no FFT throughput,
full numerical-chain, physical clock, resource, or RF qualification**.

## Evidence and reproducibility

Final command (run from this FW worktree, with a previously absent basetemp):

```sh
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -m pytest -q tests/test_starlink_bank_arithmetic_offline.py tests/starlink_oracle/test_payload_bubbles.py tests/starlink_oracle/test_forward_retirement.py --basetemp=hdl/library/starlink_pss_acquisition/build/bank-arithmetic-offline-v8 --junitxml=reports/experiments/20260910-bank-arithmetic-offline-v8.xml
```

Ruff passed for the new policy. Raw attempts v2–v8, XML v1–v8, and final sources
are in `reports/experiments/20260910-bank-arithmetic-offline-evidence.tgz`:
**11,770,952 bytes; 5,850 safe unique regular-file members**, all member hashes
rechecked; SHA256
`08c2720c9f7d639548836427d079f5c720ecb64c60bf5f3feb8f203b11dee316`.
The adjacent `20260910-bank-arithmetic-offline-results.json` contains all hashes,
31 final source paths, 62 final simulation inventories, and terminal receipts.
Each new final simulation freezes complete simulator inputs plus the 15 actually
imported repository Python modules before execution, then rejects missing/extra
files or hash changes. Installed tools/third-party packages are not archived;
earlier attempts and unchanged baseline tests do not retroactively gain this
new per-case Python import freeze. The frozen old-round reference is included.

Initial v1 had 3 static passes and 12 setup errors because the build parent did not
exist; no simulator ran, XML is retained, and tee could not create a raw stdout
file. After the directory/import-order repair, v2–v8 passed their respective
15/8/20/63/99/101/101-test scopes. Packaging initially rejected duplicate pytest
`current` symlink aliases; excluding those aliases resolved inventory counting
without modifying any test source or raw attempt.

## Remaining gate

An authorized actual-core test must omit/reject the synthetic interface, bind
the immutable generated FFT, and independently check forward/product/inverse
values, exponents, positions, scores and latency-sensitive current/late faults at
the real service cadence. New compatible-core/private-bubble DSP mapping and bank
BRAM-to-DSP timing cannot be inherited from the older standalone physical study.
No actual-core or physical run is authorized by this receipt. Continuous canonical
15 MS/s at source 15/30/60, native-rate fine samples, independent 2.5 MS/s pilot,
.18 before .17, and eventual eight-target/120 ms/300 s operation remain open
system requirements, not replaced by these offline checks.
