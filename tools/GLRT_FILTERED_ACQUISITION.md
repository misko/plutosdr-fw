# GLA2 filtered acquisition coordinates

`starlink_glrt_local_control` supports one direct 2.5-MS/s profile and two
filtered profiles: native 5 or 15 MS/s, reduced to a 2.5-MS/s acquisition lane.
The new profiles use **GLA2-1.0**. Direct 2.5 MS/s retains **GLA1-1.0** exactly,
including its magic, zero reserved words, cadence and register values.

This is a controller/event-decoder component. Complete receiver, driver, IIO
closure, native handoff and deployment integration remain necessary. The AXI
receiver's existing rate guards still reject higher-rate local capture. Neither
an isolated component test nor a GLA2 record advertises a deployed rate.

## Input ownership and sample geometry

The controller consumes only fully supported 2.5-MS/s DDC samples. For the
filtered profiles each input index is the **newest native ADC sample used**
for that filtered output, on the DDC's absolute phase-zero emission grid.
Source ownership must exclude startup outputs with `output_support=0`, fence
gaps/faults, drain the filter pipeline at STOP and bind saved native and coarse
IQ to the same visit. The controller does not infer those facts from an index.

| Native rate | Index stride | Group delay in native samples | Required prior native samples |
| --- | ---: | ---: | ---: |
| 5 MS/s | 2 | 100 | 200 |
| 15 MS/s | 6 | 318 | 636 |

The 5-MS/s bank is the existing 201-tap Q17 filter. The 15-MS/s cascade adds
the separately frozen 37-tap Q17 first stage before that same final filter.
The parent capture manifest must pin both coefficient hashes and the RX rate.

Cadence and window counts remain **coarse output counts**, with nominal
250,000-sample opportunities and 14,000-sample windows. Missing an opportunity
does not move the cadence. The source continuity check advances by the native
stride and rejects all unsigned counter-wrap residues, including wraps to a
nonzero index. Coarse timing hypotheses and CFO grids retain their 2.5-MS/s
meaning. Merely multiplying the coarse epoch does not prove native refinement.

## GLA2-1.0 record and register additions

Records contain 16 little-endian 32-bit words. Words 1–12 retain GLA1's visit,
sequence, flags, scores, CFO units and coarse window count. Word 0 is
`0x474c4132`; words 3/4 are the native coordinate of the first filtered output.
Words 13, 14 and 15 contain native rate, index stride and group delay,
respectively. These fields are mandatory and must match one supported profile.
An empty decision retains flags 3 and zero CFO/scores, with the same mandatory
profile metadata. GLA1 decoders must reject the new record magic.

The local register page retains word addressing and queue commands. Register
word 0 returns the selected magic and word 1 returns `0x00010000`. Word 21
remains the acquisition rate, 2,500,000. New GLA2 words 29/30/31 report native
rate/stride/delay; all three remain zero for GLA1. Existing snapshot counters
retain their coarse-sample/record units. First/last source coordinates are native
indices under GLA2. Any future IIO snapshot/closure format must explicitly name
GLA2 and these units; it cannot reuse the GLA1 closure decoder.

`FilteredLocalEvent.decode` validates the complete event and profile without
rewriting it into a GLA1 record. For coarse offset `q` in Q16 samples, the
native signal-center coordinate is exactly
`((first - delay) << 16) + q * stride`. Integer arithmetic preserves large
source indices and fractional low bits. Required retained native coverage is
`[first - 2*delay, first + 13999*stride + 1)`. Decode checks geometry; the
separate support check verifies this interval, and capture ownership must still
attest IQ identity and continuity. Template origin, filter mismatch and seed
convergence require numerical qualification before native jobs are admitted.

## Verification

Component tests cover both profiles, original GLA1 rejection rules, payload
validation, exact Q16 mapping, filter support boundaries and unsigned wrap.
The real numerical controller test runs unchanged coarse/verification arithmetic
at all three index strides, compares every candidate and decision word against
the independent numerical oracle, and holds the reader long enough to exercise
queue backpressure. Input IQ is already at 2.5 MS/s in that test: it verifies
the controller's mapping, not an integrated physical DDC or radio capture.
