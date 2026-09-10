# Idle mailbox admission — retained synthesis evidence

Experimental firmware only; DO NOT MERGE into main. This is structural and
functional evidence, not complete-receiver timing, CDC, IIO, RF or deployment
qualification.

`20260909-idle-mailbox-guard-synthesis.tgz` retains the exact guard, measurement
scripts, synthesis scopes, utilization reports and four actual Vivado 2022.2
functional netlists. It contains no firmware image or routed checkpoint.

- `phase-guard-synth-v1`: current guard with phase-input mode 0/1, idle mode 0.
- `idle-guard-synth-v1`: current guard with idle-mailbox mode 0/1, phase mode 1.

The source SHA256 is
`116aab63f3f0c74e590ee384d5afb7ae996dbf863554afb5a4d17684b498ba1d`.
The archive SHA256 is
`05ae6c6b4081b7fc81db8093dcb40c56dac81b929e3dc5933b3a34a8d407f083`.

## What was measured

Both idle-mode variants use 111 LUTs, 180 registers and no DSP or block RAM in
this isolated synthesis. Enabling the mode removes the full current mailbox
fault port from the `job_ready` combinational fan-in, replacing it with the
explicit idle predicate. The full current fault remains in nonfinal retirement,
final publication and fault-reason bit 0. It is not removed from the entire
guard or from all state-control paths.

The real-link premise is that current output framing faults require a private
write, and a private write requires an active guard. Admission and ACK release
require inactivity. Sticky mailbox faults are still included in those phases.
The generic guard defaults to the original unrestricted checks; opting in
without satisfying this premise is invalid.

The source-equivalence tests restore only the exact additive idle predicate
delta and compare the complete result with frozen HDL `eb96c647`. Independent
tests exercise default 0/1/X/Z pin inertness, explicit full-tuple callers, real
dual-clock private banks, late ACKs, current-link corruption and mutation
witnesses that remove sticky/final fault coverage.

Actual idle-mode netlists replay 256 jobs / 131072 words each against the
immutable `ff4229` public guard. The enabled netlist also runs a real mailbox
with frozen `eb96c647` public control/payload checks: 1536 healthy published
words and six nonfinal/final link-corruption cases with same-edge reason 01.
Its phase observations use the independent reference's state, not assumed
internal synthesized names. UNISIM's documented-in-source 100 ps Q delay is
observed after 200 ps on the same edge; no fault expectation is postponed by a
clock cycle. Separate actual FFT-service tests check the actual caller premise.

## Replaying after relocation

From this firmware checkout, with Vivado 2022.2 and its simulation libraries:

```bash
replay_dir=$(mktemp -d /tmp/starlink-idle-replay.XXXXXX)
tar -xzf reports/experiments/20260909-idle-mailbox-guard-synthesis.tgz -C "$replay_dir"
STARLINK_PSS_PHASE_INPUT_NETLIST_DIR="$replay_dir/phase-guard-synth-v1" \
STARLINK_PSS_IDLE_MAILBOX_NETLIST_DIR="$replay_dir/idle-guard-synth-v1" \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -m pytest -q \
  tests/starlink_oracle/test_phase_input_contract.py \
  tests/starlink_oracle/test_idle_mailbox_netlist.py
```

Tests require the current guard bytes to match the frozen source hash and each
netlist to match its measured hash. Recorded original paths are provenance,
not a requirement to retain the original temporary directory. If the guard
changes, regenerate the evidence instead of relaxing those checks.
