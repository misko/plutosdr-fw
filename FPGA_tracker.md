# FPGA tracker execution and evidence ledger

Canonical design specification: [FPGA_tracker_60MS.md](FPGA_tracker_60MS.md)

Status: active experimental implementation. **DO NOT MERGE INTO FIRMWARE MAIN.**

Authorized radio: `104000bac4950008230026001b440a003a` only.

## Current baseline

- Firmware branch: `codex/starlink-rx-only-do-not-merge`
- Routed 15 MS/s acquisition image:
  `v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v6`
- Physical RFIC evidence: AD9363A
- Persistent runtime target: `ad9361-1r1t`
- Persistent firmware:
  `v0.48-plutoplus-spf-iq-direct-async-v3`
- Persistent QSPI FIT SHA-256:
  `db777ac93d5c6f0be0cf2799808a4d06fe39264ee1e99e76001509394d75f1df`
- PPU setup receipt:
  `/home/mouse9911/pluto-state/starlink-rx-only-dnm/setup-ad9361-1r1t-20260906/state/setup/receipts/e1ded32ce93644efbfe8b1274a13a204.json`

## Gate ledger

| Gate | State | Evidence required |
| --- | --- | --- |
| M0: AD9361-personality DNM lifecycle | In progress | Offline plan tests, exact-target RAM boot, recovery to persistent `ad9361-1r1t` |
| M1: 120-second continuous map consumer | In progress | Controller tests, zero-loss hardware receipt, recovery proof |
| M2: deterministic 15 MS/s timing | Pending | Simulation and FPGA injection timing within one canonical sample |
| M3: cabled-RF 15 MS/s timing | Pending | Positive/negative cabled receipts |
| M4: live-LNB 15 MS/s timing | Pending | Repeated on-channel trajectory and off-channel control |
| M5: 30-to-15 decimator/index mapping | Pending | Bit-exact oracle and routed evidence |
| M6: sparse 30 MS/s refinement | Pending | Direct-oracle timing within one source sample |
| M7: 60-to-30-to-15 cascade | Pending | Bit-exact cascade and routed evidence |
| M8: sparse 60 MS/s refinement | Pending | Direct-oracle timing within one source sample |
| M9: live 60 MS/s narrowband run | Pending | 120-second receipt and rollback proof |
| M10: SSS/final frame lock | Pending | Separate frozen policy and live qualification |

## M0/M1 implementation record

The existing acquisition library already provides:

- exact ABI/rate/DDC-contract validation;
- atomic health snapshots;
- oldest-ready-bank selection;
- coherent 20,000-word copy followed by exact-bank release;
- adjacent generation and 1,280,000-sample start-index checks;
- three-map sliding-window storage;
- seven-hypothesis drift extraction; and
- candidate statistics without a detection or frame-lock claim.

The remaining implementation is:

1. make candidate generation and the DNM launcher explicitly bind
   `ad9361-1r1t` and its exact runtime model;
2. add a bounded continuous controller command that leaves acquisition enabled,
   copies/releases every map, extracts a candidate from every ready three-map
   window, and emits a final health/continuity summary;
3. add a receipt-bound host launcher that uploads that controller only to
   `/tmp`, uses PPU's exact radio and route locks, restores RX settings, removes
   the temporary binary, and requires separate PPU recovery; and
4. run the complete offline and exact-radio 120-second gates.

Implemented offline on 2026-09-06:

- candidate generation now explicitly seals either `ad9363a-1r1t` or
  `ad9361-1r1t`, including the matching live model, while defaulting to the
  historical AD9363A behavior;
- the v8 DNM launcher scopes the inherited v6 lifecycle to the exact
  `ad9361-1r1t` runtime and restores every inherited identity constant;
- `starlink_pss_acqctl monitor` continuously copies/releases maps for a bounded
  interval, computes each three-map candidate window, and emits strict NDJSON
  map and cutoff-health records;
- the host monitor seals the controller binary, PPU handoff, radio identity,
  duration, output receipt, and explicit confirmation before hardware access;
- the host validator requires approximately the rate-derived map count, every
  adjacent generation and 1,280,000-sample index step, zero fault counters,
  exact cleanup, and no PSS/SSS/frame-lock claim; and
- the future 60 MS/s gate now correctly requires wider or resettable hardware
  counters because the current DDC counters saturate rather than wrap.

Offline evidence:

- strict host and static ARM controller builds: PASS;
- native C acquisition/controller self-tests: PASS;
- ASAN/UBSAN acquisition test: PASS;
- focused M0/M1 Python tests: 40 passed;
- complete `tests/test_starlink_pss*.py` regression: 118 passed.

Hardware has not been accessed by this implementation checkpoint. M0 and M1
remain open until the exact AD9361-personality RAM lifecycle, 120-second soak,
and QSPI recovery receipts pass.

No M0/M1 result is a PSS-detection, SSS, or frame-lock claim.

## Evidence log

Add immutable commit IDs, manifests, build hashes, plan/receipt hashes, radio
observations, and recovery results here as gates close. A gate changes to
`Complete` only when every corresponding requirement in
`FPGA_tracker_60MS.md` has direct evidence.
