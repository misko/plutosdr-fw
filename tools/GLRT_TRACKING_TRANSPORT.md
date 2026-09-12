# GLT1 v1.0 multirate tracking transport

GLT1 is an additive scheduled-result contract. GLS1 and GLN1 retain their
published 60-MS/s meanings. This implementation supplies a result producer,
offline decoder and radio C association port; Linux attributes and integrated
receiver/controller deployment are subsequent work. The text submit format
below is specified here but is not yet an available radio attribute.

Each queue record is 128 bytes, 32 little-endian unsigned 32-bit words:

| Words | Meaning |
|---|---|
| 0 | Magic `0x474c5431` (`GLT1`) |
| 1–2 | Admission sequence, nonzero descriptor tag |
| 3–4 | Integer source start, least-significant word first |
| 5–6 | Carrier phase seed, phase step (modulo 2^32) |
| 7–8 | Accumulated sample count, fault bits |
| 9–12 | Signed reference I and Q sums, two words each |
| 13–16 | Signed delay I and Q sums, two words each |
| 17–22 | Signed reference I and Q prefix integrals, three words each |
| 23–24 | Unsigned observed energy |
| 25–26 | Source samples/second, full pilot samples |
| 27–28 | Repeat within descriptor (0–63), reference phase |
| 29 | Reference ROM SHA256 first eight hexadecimal digits as a u32 |
| 30–31 | Version `0x00010000`, reserved zero |

Qualified geometries are `(rate, samples, phases)` = `(2500000,3300,4)`,
`(15000000,19800,1)`, `(30000000,39600,1)`, `(60000000,79200,1)`.
At 2.5 MS/s the bank discriminator is `dc509401`; other profiles use `b04a2fab`.
The full reference hash must separately match the attested firmware manifest
and the solver profile before establishing a source epoch. This short field
detects configuration mistakes; it does not attest the loaded coefficients.

For `b=ceil(log2(samples))`, sum widths are `35+b`, prefix widths `35+2*b`,
energy width `36+b`. All unused high bits must canonically sign/zero extend,
including the entire third prefix word for the 59-bit 2.5-MS/s accumulator.
Fault bits 0–7 retain native engine meanings; bit 8 means scheduled abort and
bit 9 means source loss. Other bits are invalid. A fault-free result must have
the full sample count; partial/empty faulted results are retained and rejected
for estimation. Empty results require zero moments. Faults never bypass width,
geometry, count or association validation.

The text head is `GLT1 00010000 EPOCH WORD0 ... WORD31`, where each numeric
field is exactly eight hexadecimal digits. Epoch is external to the compact
queue record, as with GLS1; the source owner must fence configuration, reset,
rate changes and source discontinuities. The descriptor also contains that
epoch. Persist raw head plus epoch and pinned deployment identity before
acknowledging `EPOCH SEQUENCE` (eight hexadecimal digits each).

The submit text is `GLT1 VERSION RATE BANK EPOCH TAG START FRACTION PERIOD STEP
DELTA SEED REPEATS EXPIRES`, followed by newline. VERSION, RATE and BANK are
eight-digit hex; remaining fields are unsigned hex without a prefix, bounded
by the C batch field widths. RATE/BANK must match the fixed hardware profile.
START plus FRACTION/65536 is a native sample coordinate; PERIOD is Q16 native
samples. STEP and DELTA are modulo-48 Q16 carrier phase increments.

Round each absolute prediction to the nearest reference phase, ties to even;
do not repeatedly round the period. For 2.5 MS/s, reference phase 0/1/2/3 means
0/100/200/300 ns delay from the integer source start. Other rates use phase 0.
The last observed sample must be within EXPIRES without u64 wrap. Association
checks epoch, tag, admission sequence, rate, repeat, integer start, seed, phase
step, reference phase, version, bank and expiry before estimation. Reference
delay is added once to the solved timing correction. The CFO observation time
remains the center of the original IQ window.

The RTL `TRACKING=1` option selects GLT1 and scales schedule geometry for the
fixed SOURCE_RATE. It exports the scheduler phase to the engine and serializes
the engine's captured result phase. Default `TRACKING=0` retains GLS1 and its
legacy field layout. The 32-word queue size and reservation rules are unchanged.
