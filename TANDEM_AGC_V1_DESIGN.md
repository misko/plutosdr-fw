# Tandem AGC v1 — design contract

Status: **draft for review**. This document must be reviewed and frozen before any
RTL is written. Nothing here may be changed silently once RTL exists; changes go
through a revision entry at the bottom.

Baseline: gain-series-v4 **RC17**, firmware `1f3fe0cbe865df0a8793e0fd0096368d02d28a14`.
Branch: `feature/firmware-tandem-agc-v1`.
Companion plan: `tandem_agc_plan.md` revision 6.

---

## 0. What this design does, in one paragraph

An FPGA block takes ownership of the four AD9361 `CTRL_IN` pins and steps the RX1
and RX2 manual gain indices **together**, keeping both receivers at one common
index. It decides from the AD9361's own overload and low-power detectors, exposed
on `CTRL_OUT` page `0x03`. Every accepted transition is timestamped against the
64-bit FPGA sample counter and pushed into an event FIFO that software drains into
the existing, currently-unpopulated protocol-v3 gain-event array. When disabled —
which is the reset, boot, and failure state — the PS retains the pins and behaviour
is bit-for-bit what RC17 does today.

## 1. Decisions frozen by this document

| # | Decision | Value | Why |
|---|---|---|---|
| D-1 | Controller clock domain | **`l_clk`** (the AD9361 `DATA_CLK`, RX datapath clock) | Keeps decisions and timestamps in the same domain as the sample counter, removing a CDC from the timestamp path. Also gives the narrowest pulse-width register. |
| D-2 | Pulse width register | **8 bits**, default **16**, RTL floor **4** | `N_min = 4 / rx_fir_dec` on `l_clk`; worst case is `rx_fir_dec = 1`, which is the device-tree boot default. Default 16 is 4× margin. 8 bits also covers a hypothetical LVDS switch (`N_min = 8`). |
| D-3 | Event sample counter width | **64-bit**, full width, in the FIFO and on the wire | The wire record already carries `uint64_t sample_sequence`. Carrying 64 bits internally makes counter rollover a simulation-only concern (~9,500 years at 61.44 MS/s) instead of a live 70-second hazard. |
| D-4 | Event sequence width | **32 bits**, wrap handled by serial-number comparison | Same technique RC17 uses for request-ID wrap. Fits the 6 free bytes of the existing wire record. |
| D-5 | Ownership epoch width | **8 bits**, never zero, skips zero on wrap | Transposed from RC17's `generation`. Lives in the FIFO record and the frame header, **not** in the 16-byte wire record — there is no room, and stale-epoch events are dropped at drain so the wire never sees them. |
| D-6 | Gain step size | **1 index = 1 dB**, both directions | Must be programmed explicitly: the shipped configuration currently moves **2** indices per edge. One index per pulse makes the FPGA model trivially auditable. |
| D-7 | Minimum index clamp default | **30** | The audited tables change the LNA word only at indices 8, 20 and 30. Clamping at ≥30 makes the L6 LNA-bypass phase inversion structurally unreachable, and independently keeps operation inside one frozen `(LNA, MIXER, TIA)` state, which measurement associates with a 3.3× smaller high-band phase residual. Free given the 27–73 dB range in use. |
| D-8 | Maximum index clamp default | read from the device | `Maximum Full Table/LMT Table Index`, chip default 76. Never hard-code. |
| D-9 | Event FIFO geometry | **256 deep × 128 bits** | 32,768 bits = exactly one BRAM36. Depth is ~15× the worst-case per-frame event count (see §7.3). Matches `SPF_MAX_GAIN_EVENTS`. |
| D-10 | Cooldown timebase | **power-measurement periods**, not clock cycles | The low-power flag only updates once per decimated power-measurement period (256–410 µs at every supported rate). A cooldown in microseconds is meaningless against it. |

## 2. Modes and lifecycle

### 2.1 Mode set

| Mode | Meaning |
|---|---|
| `legacy` | PS owns the pins, AD9361 pin control disarmed, FPGA outputs inactive. Reset, boot, upgrade and failure default. |
| `tandem-hold` | FPGA owns the pins and holds all four low; both receivers sit at one verified common index; no automatic steps. |
| `tandem-auto` | As above, plus the policy runs and may emit pulses. |

There is one global mode. There are deliberately **no** per-channel controls — a
per-channel API would permit exactly the divergent state this feature exists to
prevent.

### 2.2 Lifecycle states

Transposed directly from RC17's `spf_ip_rx_lifecycle`, which solves the same
problem — a hardware ownership handoff whose control plane must stay responsive
while slow hardware work proceeds — and is hardware-qualified on these radios.
Divergences from RC17 are listed in §2.4 and nowhere else.

| State | RC17 equivalent | Meaning |
|---|---|---|
| `LEGACY` | `IDLE` | PS owns pins; pin control disarmed |
| `ARMING` | `STARTING` | SPI transaction sequence running; pins not yet transferred |
| `OWNED_IDLE` | `ARMED` | FPGA owns pins, holds low, consumer ready, pin control armed. This is `tandem-hold` |
| `ACTIVE` | `RUNNING` | Policy running, pulses permitted. This is `tandem-auto` |
| `DISARMING` | `STOPPING` | Disable requested; finishing any pulse in flight, running teardown |
| `RELEASABLE` | `REAPABLE` | All hardware state released, awaiting completion event |
| `FAULTED` | `FATAL` | Sticky fault disarmed the controller; requires explicit operator recovery |

```
   ┌─────────┐  enable   ┌─────────┐  consumer+SPI ok  ┌────────────┐
   │ LEGACY  │──────────▶│ ARMING  │──────────────────▶│ OWNED_IDLE │
   └─────────┘           └─────────┘                   └────────────┘
        ▲                     │                          │       ▲
        │                     │ any step fails           │ run   │ hold
        │                     ▼                          ▼ gate  │
        │                ┌──────────┐               ┌────────┐   │
        │                │ DISARMING│◀──────────────│ ACTIVE │───┘
        │                └──────────┘   disable     └────────┘
        │                     │                          │
        │                     ▼                    fault │
        │              ┌─────────────┐                   ▼
        └──────────────│ RELEASABLE  │             ┌──────────┐
           completion  └─────────────┘             │ FAULTED  │
                                                   └──────────┘
                                              (operator recovery only)
```

Entering `ARMING` increments the ownership epoch.

### 2.3 Mechanisms adopted from RC17

- **Ownership epoch, never reused.** Increments on every entry to `ARMING`, skips
  zero on wrap. Every event record and every acknowledgement carries it. Anything
  bearing a retired epoch is counted and discarded, never applied. This is what
  prevents a late acknowledgement, or an event left in the FIFO from a previous
  arm, being attributed to the current session.
- **Completed-session tombstone.** The last retired epoch is retained. A delayed or
  duplicated disable request for it is answered successfully and idempotently
  without disturbing a session armed since.
- **Distinct, non-consuming handshake signals.** Separate `armed`, `run`, `disarm`
  and `released` signals. RC17 used four distinct eventfds precisely so one
  lifecycle signal could not consume another's state; a single shared ready/ack
  bit is the bug it fixed.
- **Readiness before release.** The event consumer must be running and accepting the
  current epoch before ownership transfers, and ownership must transfer before pin
  control is armed. Success is reported only after the armed acknowledgement is
  accepted, and only then is the policy gate opened.
- **Completion only after release.** `released` asserts only after the pulse
  generator is quiescent, pin control is disarmed, ownership has returned to the PS,
  and the legacy gain mode is restored.
- **Bounded, state-specific busy.** Retry is permitted only against `ARMING`,
  `DISARMING` and `RELEASABLE`. Never against `FAULTED`, and never unbounded.
- **Never report success early.** If teardown cannot complete, the reported state
  stays `DISARMING` or becomes `FAULTED`. The design never claims the pins are
  released when it is not certain. As in RC17, a stuck teardown leaves the service
  supervisor as the recovery boundary; that is accepted, not designed around.

### 2.4 Deliberate divergences from RC17

| Divergence | Reason |
|---|---|
| Ownership is a hardware mux, not a software flag | The resource is four pins with a tri-state, not a DMA device node. §4. |
| No request-replay ring inside the FPGA | Replay is a control-plane concern. If tandem control is exposed over the UDP control plane it **must** reuse RC17's existing replay discipline unchanged; a second, differently-behaved replay implementation on the same socket is a defect. |
| Epoch is 8 bits, not 64 | It only has to disambiguate arms within one boot, and it must fit a FIFO record and a header field. |

## 3. AD9361 hardware contract assumed by this design

Every item is verified; see the plan's Appendix A for sources. RTL and the runtime
must both hold to these.

| Item | Value |
|---|---|
| `CTRL_IN0` / `1` / `2` / `3` | RX1 increase / RX1 decrease / RX2 increase / RX2 decrease |
| Pin mapping | identity: `gpio_ctl[0..3]` → `CTRL_IN0..3`, verified at net level against the Pluto+ schematic |
| EMIO bits | `gpio_ctl` → `[11:8]`, `gpio_status` → `[7:0]` |
| Linux GPIO | `CTRL_IN` = `<&gpio0 62..65>` = global 968..971 (discover the base at runtime) |
| Pulse rule | asynchronous, edge-detected; high and low each ≥ 2 ClkRF cycles; no setup/hold to any clock |
| `ClkRF` | `sample_rate × rx_fir_dec`; `f_l_clk = 2 × sample_rate`; ratio `= 2 / rx_fir_dec` |
| Detector page | `0x035 = 0x03`, enables in `0x036` |
| Page `0x03` bits | D7..D0 = CH1 low power, CH1 large LMT, CH1 large ADC, CH1 small ADC, CH2 low power, CH2 large LMT, CH2 large ADC, CH2 small ADC |
| Overload semantics | latch high until the gain changes, then held in reset until Peak Overload Wait Time expires |
| Low-power semantics | **unfiltered in MGC**; updates once per power-measurement period |
| Live MGC thresholds | `0x104` small ADC, `0x105` large ADC, `0x108` large LMT, `0x114` low power |
| Pin-control arm | `0x0FB[1:0]`, read-modify-write only |
| Gain table | full table mandatory; band-dependent at 1300 and 4000 MHz; 1 index = 1 dB |

**Not available, and therefore not designed around:** small-LMT overload (on no
`CTRL_OUT` page at all), and any real-time gain-index readback (no page carries both
channels, and those that carry one give only bits `[6:2]`).

## 4. Ownership mux

Inserted between the PS EMIO GPIO and the existing `ad_iobuf` in
`projects/pluto/system_top.v`, on **bits `[11:8]` only**. Bits `[7:0]`
(`gpio_status`) and `[13:12]` pass through untouched.

The mux owns **both** the output value and the tri-state:

```
  PS gpio_o[11:8] ──┐
                    ├── mux ──▶ ad_iobuf .dio_i[11:8]
  FPGA pulse_o ─────┘

  PS gpio_t[11:8] ──┐
                    ├── mux ──▶ ad_iobuf .dio_t[11:8]
  FPGA pulse_t ─────┘
```

Owning only the value is insufficient: the pins reset to high-Z and the PS leaves
them as inputs, so without taking the tri-state the FPGA's drive never reaches the
AD9361.

Rules:

- **Reset selects legacy** for both value and tri-state.
- The select is a single registered bit in the `l_clk` domain. It changes only in
  `ARMING` (legacy → FPGA) and in `DISARMING` (FPGA → legacy), never combinationally
  and never mid-pulse.
- On acquiring ownership the FPGA drives all four low and holds them low for at
  least one full programmed pulse period before any pulse is permitted.
- On releasing, the FPGA drives low, then hands back value and tri-state in the same
  clock cycle.
- **The mux must never produce an edge because ownership changed.** This is a
  proof obligation on the RTL, not an aspiration: see §9 assertion A-7.

## 5. Detector conditioning and policy

### 5.1 Input conditioning

The eight `gpio_status` bits are asynchronous to `l_clk`. Each is source-registered
in the pad domain, then passed through a 2-flop synchroniser, then a programmable
digital debounce of `DEBOUNCE` `l_clk` cycles. No detector bit may reach the policy
without all three stages.

### 5.2 Sampling discipline

The overload bits are **latched until a gain change and then blanked**, so they are
not a level to be polled freely:

- Overload inputs are only *evaluated* when `blank_guard` has expired since the last
  emitted pulse. `blank_guard` is programmable and must exceed the AD9361's Peak
  Overload Wait Time, which the driver computes as `ceil(0.1 µs × ClkRF_MHz) + 1`
  and re-derives on every baseband clock change.
- A low reading during blanking is **not** "overload cleared" and must never be
  treated as such.
- The low-power inputs are sampled once per programmed `PWR_PERIOD`, expressed in
  `l_clk` cycles and defaulting to one AD9361 power-measurement period. Sampling
  faster returns the same value repeatedly.

### 5.3 Truth table

Inputs, after conditioning, per channel `c ∈ {1,2}`: `LP[c]`, `LGLMT[c]`,
`LGADC[c]`, `SMADC[c]`.

```
  DECREASE   if  LGLMT[1] | LGADC[1] | LGLMT[2] | LGADC[2]
  INHIBIT    if  SMADC[1] | SMADC[2]
  INCREASE   if  LP[1] & LP[2] & !INHIBIT & dwell_satisfied
  HOLD       otherwise
```

Priority is strict: `DECREASE` > `INHIBIT` > `INCREASE` > `HOLD`. The policy is
asymmetric by design — **either** channel may protect **both** paths from overload,
while **both** must agree before gain is increased.

`dwell_satisfied` means `LP[1] & LP[2]` has held continuously for `DWELL_PERIODS`
consecutive power-measurement periods. The AD9361 supplies no filtering here, so
this counter is the only thing preventing gain chatter on bursty traffic.

### 5.4 Accepted-transition rules

A decision becomes an accepted transition, and therefore an event, only if all hold:

1. state is `ACTIVE`;
2. `cooldown` has expired;
3. the resulting index stays within `[INDEX_MIN, INDEX_MAX]`;
4. no pulse is in flight;
5. no sticky fault is set.

If a `DECREASE` is required but the index is already at `INDEX_MIN`, no pulse is
emitted, `clamped_at_limit_count` increments, and the condition is reported. The
controller must not spin: because the overload output stays high until a gain
change that will never come, a naive implementation would retry forever.

Symmetrically, `INCREASE` blocked at `INDEX_MAX` increments
`clamped_at_limit_count`; `INCREASE` blocked by the peer's `SMADC` or by only one
channel reporting low power increments `inhibited_by_peer_count`. That second
counter matters: a strong interferer on one channel legitimately starves the quiet
channel of gain, and Campaign D must be able to distinguish that accepted behaviour
from a fault.

### 5.5 Timing constants

| Constant | Units | Default | Floor | Rationale |
|---|---|---|---|---|
| `PULSE_HIGH`, `PULSE_LOW` | `l_clk` cycles | 16 | 4 | `N_min = 4 / rx_fir_dec`, worst case `rx_fir_dec = 1` |
| `BLANK_GUARD` | `l_clk` cycles | ≥ Peak Overload Wait Time + margin | — | detector blanking window |
| `PWR_PERIOD` | `l_clk` cycles | one AD9361 power-measurement period | — | 256–410 µs at every supported rate |
| `COOLDOWN` | `PWR_PERIOD` units | **2** (≈1 ms) | 1 | must span ≥2 power-measurement periods so a post-step low-power reading is fresh |
| `DWELL_PERIODS` | `PWR_PERIOD` units | 4 | 1 | recovery deliberately slower than protection |

The asymmetry is the point: protection reacts within a blanking window measured in
nanoseconds, recovery is paced in milliseconds.

## 6. Index model and synchronisation

The FPGA holds `expected_index`, updated by exactly one step per accepted
transition, saturating at the clamps.

**Software verification is the only verification available.** No `CTRL_OUT` page
exposes a usable gain index for both channels, so the FPGA cannot self-check against
hardware. Software reads the real RX1 and RX2 indices over SPI and compares.

That read races the pulses, so the comparison is governed by a **quiescence rule**:

- compare only when the controller reports no pulse in flight **and** `COOLDOWN` has
  expired;
- inside an active window, a difference of at most one programmed step is not a
  fault;
- a fault requires **two consecutive disagreeing quiescent reads**.

A confirmed mismatch is a hard synchronisation fault: stop issuing pulses, set the
sticky fault, preserve diagnostic state, require explicit re-synchronisation.

Conflicting operations, which must be refused while tandem owns or is releasing the
pins, or must disarm tandem first:

- direct per-channel gain writes;
- gain-table changes, and any switch to split-table mode;
- **RX FIR decimation changes** — these swing the required pulse width 4×. Key the
  interlock on `rx_fir_dec`, not on sample rate: the `l_clk`/`ClkRF` ratio is
  rate-invariant. A sample-rate write must still trigger revalidation, because
  pyadi-iio's setter rewrites `filter_fir_config` and toggles `filter_fir_en` on
  *every* call, even at an unchanged rate;
- LO retunes crossing 1300 or 4000 MHz — the table reload changes what the index
  means;
- gain-control mode changes, and **`hybrid` mode specifically**, which re-arms
  `CTRL_IN2` through `0x0FA` without touching `0x0FB` and so bypasses the arming
  interlock entirely;
- a debugfs `initialize`, or a driver unbind/rebind, either of which reverts
  `0x0FB` underneath an armed controller;
- any unmasked whole-byte write to `0x0FB`.

## 7. Event records

### 7.1 Internal FIFO record — 128 bits

| Bits | Field | Notes |
|---|---|---|
| `[63:0]` | `sample_counter` | full 64-bit, captured in `l_clk` at the accepted instant |
| `[71:64]` | `gain_index` | common index **after** the transition |
| `[75:72]` | `reason` | see §7.2 |
| `[77:76]` | `direction` | 0 hold/other, 1 increase, 2 decrease |
| `[79:78]` | reserved | must be zero |
| `[87:80]` | `epoch` | ownership epoch; drain-time filter |
| `[119:88]` | `sequence` | 32-bit, monotonic within an epoch |
| `[127:120]` | reserved | must be zero |

256 × 128 bits = 32,768 bits = one BRAM36.

### 7.2 Reason codes

| Code | Reason |
|---|---|
| 0 | large LMT overload |
| 1 | large ADC overload |
| 2 | small-ADC-overload inhibit |
| 3 | both channels low power after dwell |
| 4 | increase inhibited by peer |
| 5 | clamped at configured limit while condition persists |
| 6 | initialisation / synchronisation |
| 7 | hold / resume |
| 8 | controller disabled or faulted |

### 7.3 Depth justification

`COOLDOWN` defaults to ≈1 ms, so the event rate is bounded at ~1000/s. A
524,288-sample frame at 30 MS/s spans ~17.5 ms, giving a worst case of ~18 events
per frame. Depth 256 is ~14× that, and matches `SPF_MAX_GAIN_EVENTS`.

### 7.4 Wire record

The existing `spf_gain_event_v3_t` is used unchanged in size and layout — 16 bytes,
already negotiated, already carried by `spf_radio_frame_v3_build()`, and currently
**unpopulated** (`thread_read.c` passes `gain_events = NULL, gain_event_count = 0`).
The six reserved bytes are assigned:

| Offset | Field | Source |
|---|---|---|
| `0..7` | `sample_sequence` u64 | FIFO `sample_counter` |
| `8..9` | `flags` u16 | see below |
| `10` | `gain_index` u8 | FIFO `gain_index` |
| `11` | `reason_direction` u8 | `reason` in `[3:0]`, `direction` in `[5:4]` |
| `12..15` | `event_sequence` u32 | FIFO `sequence` |

The epoch is **not** on the wire. Stale-epoch events are discarded at drain and
never reach a frame, so a per-event epoch would be redundant; the epoch in force is
reported once in the frame header's `reserved1`, which is a backward-compatible use
of a reserved field.

The existing flag bits `SPF_GAIN_EVENT_RX1_CHANGED`, `RX2_CHANGED`, `RX1_LOCKED`
and `RX2_LOCKED` retain their meaning. Under tandem both `CHANGED` bits are always
set together, which is itself the invariant that proves tandem operated.

### 7.5 Validity and overflow

`SPF_META_FPGA_EVENTS_VALID` must be driven by **"the producer was armed and drained
for this frame"**, not by a non-zero count. The current builder sets it only when
`gain_event_count != 0`, which makes a frame with a genuinely constant gain
indistinguishable from a frame where the feature is not running — and that defeats
exact reconstruction, which is the entire point. This is a required change to
`spf_radio_frame_v3.c` and it is covered by a test.

FIFO overflow sets a sticky fault, propagates `SPF_META_FPGA_EVENT_OVERFLOW`, and
increments `gain_event_overflow_count`. It is never silent.

### 7.6 Recorded instant, and what it is not

The recorded counter is the value at the moment the controller **accepts** the
transition and emits the pulse. It is **not** the sample index at which the gain
change becomes visible in the IQ stream: analog stages settle, the receive filter
chain adds group delay, and DC-offset tracking re-adapts.

Post-processing consumes *recorded counter + published offset*. Campaign C measures
that offset per gain index and per direction and publishes either a constant with a
tolerance or a table. Post-processing must never assume the two are the same sample.

## 8. Register map

AXI-Lite, 32-bit registers, offsets from the block base. `RO` read-only, `RW`
read-write, `W1C` write-1-to-clear.

| Offset | Name | Acc | Contents |
|---|---|---|---|
| `0x00` | `ID` | RO | magic + feature version |
| `0x04` | `CAPS` | RO | FIFO depth, record width, supported modes |
| `0x08` | `CTRL` | RW | `[1:0]` requested mode, `[8]` fault clear request |
| `0x0C` | `STATUS` | RO | `[2:0]` lifecycle state, `[4]` pin owner, `[5]` tri-state owner, `[6]` pulse in flight, `[7]` cooldown active |
| `0x10` | `EPOCH` | RO | `[7:0]` current epoch, `[15:8]` tombstoned epoch |
| `0x14` | `INDEX` | RW | `[7:0]` `INDEX_MIN`, `[15:8]` `INDEX_MAX`, `[23:16]` initial index |
| `0x18` | `EXPECTED` | RO | `[7:0]` current `expected_index` |
| `0x1C` | `PULSE` | RW | `[7:0]` `PULSE_HIGH`, `[15:8]` `PULSE_LOW`, `[31:16]` `BLANK_GUARD` |
| `0x20` | `PWR_PERIOD` | RW | `l_clk` cycles per power-measurement period |
| `0x24` | `TIMING` | RW | `[7:0]` `COOLDOWN`, `[15:8]` `DWELL_PERIODS`, `[23:16]` `DEBOUNCE` |
| `0x28` | `POLICY` | RW | per-detector enables, for bring-up isolation |
| `0x2C` | `FAULT` | W1C | sticky: FIFO overflow, index mismatch, consumer not ready, illegal transition, ownership timeout |
| `0x30` | `EVT_LO` | RO | FIFO read port, bits `[31:0]`; reading `EVT_HI3` pops |
| `0x34` | `EVT_MID0` | RO | bits `[63:32]` |
| `0x38` | `EVT_MID1` | RO | bits `[95:64]` |
| `0x3C` | `EVT_HI3` | RO | bits `[127:96]`; **read pops the entry** |
| `0x40` | `EVT_LEVEL` | RO | occupancy |
| `0x44` | `EVT_OVF` | RO | overflow count, saturating |
| `0x48` | `CNT_TRANS` | RO | accepted transitions |
| `0x4C` | `CNT_STALE` | RO | events/acks rejected on epoch |
| `0x50` | `CNT_INHIB` | RO | increases inhibited by peer |
| `0x54` | `CNT_CLAMP` | RO | decisions blocked at a clamp |
| `0x58` | `CNT_DUPDIS` | RO | duplicate disable requests coalesced |
| `0x5C` | `DETECT` | RO | live conditioned detector bits, for diagnostics |

Read order for an event is `EVT_LO`, `EVT_MID0`, `EVT_MID1`, `EVT_HI3`. The pop on
the final read makes a partially-read event impossible.

## 9. CDC and reset

| Crossing | Structure |
|---|---|
| `gpio_status` pads → `l_clk` | source register in pad domain, 2-flop synchroniser, then debounce |
| AXI (`s_axi_aclk`) → `l_clk` config | value register held stable in AXI domain, toggle-synchronised load pulse; no multi-bit field crosses without a qualifying handshake |
| `l_clk` → AXI status/counters | gray-coded where a count crosses; otherwise handshake-qualified snapshots |
| `l_clk` → AXI event FIFO | asynchronous FIFO with gray-coded pointers |

Reset: asynchronous assert, **synchronous deassert in each destination domain**.
Reset selects legacy ownership for both value and tri-state. The design must behave
correctly when the source clock is stopped or starts late, and under every reset
ordering permutation — RC5–RC6 showed offline-clean designs still failing on
boot-dependent clock and reset ordering.

**Hard constraint from RC7:** no controller, event, status, counter or diagnostic
signal may appear in a DMA `ready`/`valid` path. Diagnostic logic on a DMA-ready
path produced negative WNS once already; isolating it restored positive slack.

## 10. Assertions the RTL must satisfy

| # | Assertion |
|---|---|
| A-1 | increment and decrement are never asserted simultaneously on a channel |
| A-2 | the RX1 and RX2 command pairs are bit-identical on every cycle |
| A-3 | every emitted pulse satisfies `PULSE_HIGH` and `PULSE_LOW` at the programmed values |
| A-4 | `expected_index` changes by at most one programmed step per accepted transition |
| A-5 | every accepted transition produces exactly one event, in order |
| A-6 | no event exists without an accepted transition |
| A-7 | **an ownership change never produces an edge on any `CTRL_IN`** |
| A-8 | outside FPGA ownership, all four outputs are low and tri-stated to the legacy path |
| A-9 | no event carries a retired epoch |
| A-10 | the sequence number is monotonic within an epoch |
| A-11 | no pulse is emitted while `cooldown` is active or a fault is set |
| A-12 | detector inputs are never evaluated inside the blanking window |

## 11. Enable and disable sequences

Both run **outside** the control request handler. The handler accepts the request,
starts the transition, and returns — RC17's central lesson.

**Enable.** Entering `ARMING` increments the epoch.

1. controller disabled, all four FPGA outputs low
2. verify full gain table mode; read the programmed maximum index
3. place both receivers in manual gain mode
4. program the same initial index on RX1 and RX2 over SPI
5. read back both; require equality
6. configure `CTRL_OUT` page `0x03` and the output enables
7. program limits, thresholds, pulse width, dwell, cooldown, epoch, event settings
8. clear the event FIFO and sticky faults; confirm the consumer is running and
   accepting the current epoch
9. transfer pin ownership — value **and** tri-state — with outputs held low
10. **only now** arm `0x0FB[1:0]`, read-modify-write, `value | 0x03`
11. require an armed acknowledgement carrying the current epoch; report success only
    after that response is accepted; then open the policy gate

**Disable.**

1. request disable; a duplicate while already `DISARMING` is counted and coalesced
2. finish any pulse in flight
3. hold all outputs low; report idle
4. disarm `0x0FB[1:0]` **before** releasing the pins
5. return value and tri-state ownership to the legacy path
6. restore the requested legacy gain mode
7. report disarmed only after every preceding step completes; retire the epoch into
   the tombstone

The ordering in both directions is a safety requirement, not a preference. The
`CTRL_IN` pins float — high-Z from power-on through Linux, no board pull, no
internal pull in the AD9361 — so armed pin control over unowned pins is an
uncommanded gain change on both receivers driven by whatever couples into four
undriven traces.

Any failure returns to a known-safe legacy state and reports a precise error.

## 12. Open items — must be closed before RTL is frozen

| # | Item | Owner |
|---|---|---|
| O-1 | Are `CTRL_IN` edges honoured while the ENSM is outside the RX state? | bench |
| O-2 | Hold-band width between low-power de-assert and small-ADC assert. The `z` → dBFS mapping is undocumented and ADI publishes no recommended values — it brute-forces 980 combinations and disables the low-power path entirely | bench (E-GSC6 session) |
| O-3 | Measured `BLANK_GUARD` margin over Peak Overload Wait Time across the supported rate set | bench |
| O-4 | Decision-to-effect offset — constant, or a table keyed by index and direction? | Campaign C |
| O-5 | Confirm `gpio_ctl` bit order against the board constraints once more at integration, as a second witness to the schematic extraction | integration |

None of O-1 through O-5 blocks writing the standalone controller and its testbench,
because all five are parameters rather than structure. All five block the candidate
freeze.

## 13. Revision history

| Rev | Date | Change |
|---|---|---|
| 1 | 2026-08-10 | Initial draft for review. Clock domain fixed to `l_clk` per D-1. |
