# Native60 service probe: pre-evaluation contract

Frozen before any native60 RTL service execution. Preparation/compile-only and
offline policy tests are authorized; execution needs separate parent approval.
The additive probe uses the unchanged public native tracker, not PSMA, PIL1, a
bank FFT, or a newly admitted receiver profile. Upper-edge fixture only, with a
static known center, not a causal detector or RF-accuracy experiment.

Base FW `f62b0716ccf660c7aac600be00d0f063b34a3a89`, HDL
`529dc8e8d33afc237c7b26f8969ec32fa97cdbdd`. Existing numerical cohort
`build/high-rate60-offline-v2/cohort`, manifest SHA256
`6de2f3645459f8649d8fee127e479991fb1cc55b75001a37c763223e716b4dfa`,
source signature `c56f812b79f5bb8d5b60bc70af43ad0b5f1579e5af0e74dd8516fabeb2237c0a`.
All 69 numerical files and all old30 sources/goldens remain unchanged.

## Clock, source, admission and identity

The actual source oscillator is phase `2.1 ns`, half-period `#(500.0/60)` with
`1 ns / 1 fs` simulation resolution; control is `#5`. Check observed first edge,
every source half-period (8,333,333 fs rounded), full cadence (16,666,666 fs),
and 100 MHz control period with 1 fs tolerance. `RATE_MSPS=60` alone is not clock
evidence. The source clock never stops, including after source valid/enable stop.

Exactly 16,423 original raw CI16 samples cover
`[34359735211,34359751634)` with consecutive indexes/timestamps; no added tail.
The public command trigger is index `34359738560`, with actual sample-domain
handshake in closed `[34359738560,34359738720]`, signed lead `[1535,1695]`,
and no more than 256 control cycles from trigger. Capture covers
`[34359740256,34359740776)` (520 original samples); center `34359740384`.
Use all 264 coefficients, all 257 raw lags `[-128,128]` and 241 qualified lags
`[-120,120]`. Every tuple, power, saturation count and all 26 packet words must
match the existing independently generated cohort exactly.

Native wrapper: rate60, injection disabled, DSP reducer enabled. Public ID/ABI/
rate/geometry/caps are `50535354/00010003/0000003c/0f8c1108/0000001d`.
Request `60000520`, coefficient generation `60000001`, Eh `1073758594`.
Visit `60000052` is fixture context outside the 26-word packet. Source memory is
Q16:I16, coefficient memory I16:Q16; AXI coefficient writes explicitly swap the
two halves. Raw lag wire is signed9, frozen lag memory signed32; validate the
sign extension, not a truncation-warning waiver. Saturation wire9/memory12 must
have known-zero unused high bits.

## Independently readable state-to-budget derivation

All units below are 100 MHz control/engine cycles from the final captured sample.
This is a conservative predeclared bound, not a fit to measured RTL service.

| Work | Unchanged state path / assumption | Cycles |
|---|---|---:|
| Capture transfer | `capture_bridge` ISSUE/WAIT/SEND for520 words, plus64 descriptor CDC/start | 1,624 |
| Sample energy | `sliding_correlator` SAMPLE_ENERGY for520 words, plus16 synchronous-read/MAC/flush | 536 |
| Complete raw sweep | 257 × (264 CORRELATION issues +16 read/MAC/FLUSH/FINALIZE/EMIT/SLIDE +16 DSP reducer wait) | 76,072 |
| Publication | Free result store, CDC/IRQ allowance | 128 |
| Derived total | Includes all257 raw lags, not only264×257 MAC issues | 78,360 |

Correlator `STATE_EMIT` waits for ready. DSP reducer has the bounded
IDLE/SQUARE_RE_WAIT/CAPTURE/SQUARE_IM_WAIT/CAPTURE/PREPARE/LEFT_WAIT/CAPTURE/
RIGHT_WAIT/COMPARE/DECIDE/ACCEPT/OUTPUT chain. The16-cycle per-lag allowance is
conditional on one healthy configured job and a free result bank; no competing
commands, public reader arbitration or deliberate result backpressure.

Both first publication and full257 drain plus engine/bridge idle must occur
within84,000 cycles. Public readout/release must finish within88,000 cycles:
`84000 + 140*24 + 32 retention + 24 release settle = 87416 <= 88000`.
Two complete indexed26-word public reads consume104 transactions; release and
any admitted telemetry share the140-transaction ceiling. Every transaction has
its own24-cycle bound. Configure before source begins; coefficient generation
polling has at most2000 public reads. Global watchdog160,000 control cycles.

Only10,858 source samples remain after capture; they do not cover this full
service bound. Source valid/enable stop after the exact finite source, while the
sample clock remains running for CDC and compute. Record actual post-source-off
compute separately from legitimate pre-command coefficient preparation.

## Completion and no-stale policy

The241st qualified raw tuple is lag120. It may publish a result while the final
eight unqualified raw tuples (lags121..128) are still being computed. A published
or released packet is therefore insufficient completion evidence. Require every
raw handshake through lag128, full raw count257, qualified count241, engine idle,
bridge idle with no pending sample/start, and one actual command/capture only.

Retain the result for32 control cycles between identical26-word reads; release
through public AXI and settle24 cycles. Allow raw tail drainage before or after
public release, subject to the independent84,000-cycle full-drain bound.
After source off, release AND full drain/idle, observe exactly256 further control
cycles with no tuple, capture, command, IRQ, result or engine work; require the
sample clock to continue throughout. Known-zero health is mandatory throughout
the configured epoch, with no X/Z truthiness acceptance. Frozen acceptance is
not extended after a failure. Failures, source pre/post receipts and all actual
raw tuple/packet/clock/admission/lifecycle evidence must be retained.
