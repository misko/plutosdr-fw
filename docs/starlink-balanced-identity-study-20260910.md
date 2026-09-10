# Balanced identity equality: tested, no physical measurement

Tested source: FW `d233ba2f62afccde1ef2fd053967e3604b3245c3`, HDL
`447183b84250595be5324556f65145d130aca453`. This is a separate checkpoint
after held-phase-only FW `1530939fb` / HDL `3c5c3aba` (design `d99c251e`).
The previous failed physical reports and sources remain unchanged.

`BALANCED_IDENTITY_EQ=0` retains the original full input identity equality.
Only the registered bank-owned wrapper opts in. All 70 bits are partitioned
into 24 kept leaves (23 three-bit equalities and bit69), four kept six-way
reductions, and a final AND. There is no added register, hash, phase exemption
or logical latency. Ordinal/TLAST, current fault, delivery demand, duplicate,
certificate, complete and sticky reason logic are unchanged. Three LUT layers
is the intended equality mapping, not a measured resource/timing result.

## Exact contract and negative witnesses

A frozen `d99c251e` input guard is checked byte-for-byte against that git pin,
apart from its module name. A strict inverse adapter removes only the exact
new parameter/range check/combinational block and restores the old equality;
the entire remaining guard must match. The entire wrapper must likewise match
`d99c251e` after removing only its registered-only parameter connection.
Historical cursor/held-only structural tests compose these exact adapters;
their original whole-body comparisons and behavioral rejection requirements
remain, with no new skips or relaxed assertions.

Both default and balanced modes pass 420 single-bit corruption rows each:
every bit0 through69, first/interior(37)/final(511) slot, ready low/high.
Each makes 163,293 full checker-output comparisons against the frozen guard,
including current events, exact sticky reasons, certificates, transport/checker
readiness and payload. Every fault is quarantined until reset; healthy terminal
recovery is checked. Omitting the final bit69 leaf is rejected at
`BALANCED_IDENTITY_MISMATCH bit=69 slot=0 ready=0`, before a healthy receipt.
Unsupported parameter2 is also rejected.

Existing immutable-cursor witnesses pass with identity checking enabled and
disabled, covering legal stalls, missing valid/enable demand, ordinal/TLAST,
duplicate starts, first-word idle, completed-input idle and reset recovery.
The balanced simultaneous-terminal input/result suite retains 58,076
comparisons, 15,433 return checks, four healthy cases, 26 rejected cases and
three commits. It covers legal final input/first output and malformed
identity/ordinal/TLAST on that same edge. The duplicate-veto omission mutant
still fails its exact `phase=2 kind=0` witness.

Full regression: **258 passed, eight unchanged explicit physical-test skips**.
All nine new balanced tests pass; Ruff and diff checks pass. There was no RTL
correction or failed normal test/actual-core attempt in this step. Expected
mutation/invalid-parameter failures are retained in the evidence, not hidden.

## Actual-core and control trace evidence

Fresh actual Vivado2022.2 simulations at100/175 MHz pass in both modes. The
actual benchmark explicitly checks balanced mode1 in registered operation and
mode0 in both the legacy shadow and default wrapper. Registered mode makes
1,073,334 paired checker checks; default makes649,219. The full held-phase tuple,
12 real-bank active identity/ordinal/TLAST corruptions, vendor-only open-slot
QUARANTINE, reset, public result/reason and ACK witnesses all pass unchanged.
The registered84-row preflight matrix and60/12/60 private counters are unchanged.

Original arithmetic/metadata receipts remain44 healthy blocks/10 faults,
24,064 forward/product words and22,658 inverse words, including130 provisional
prefix words, exactly against the unchanged frozen goldens. This slice has no
score normalizer; this is not a new whole-score or receiver integration result.
Nominal intervals remain4,540 default/4,548 registered clocks. The complete
24-column control traces byte-match the corresponding held-only runs, including
their fault/private-state traces, not just healthy throughput.

Original runs: `/tmp/starlink-completed-input.5EaJuD/balanced-actual-v1` and
`balanced-default-v1`. Original sessions98874/46077 exited zero at03:02:55 /
03:01:45 UTC. Their raw receipts are under
`project/fft_bank_owned_slice.sim/sim_1/behav/xsim/simulate.log`.

| Artifact | SHA256 |
| --- | --- |
| Wrapper | `929cd9d2387ba5c228134c4ace73b5de458cabb8ec05c7431342b06cbef15c69` |
| Input guard | `eb1f968a30ae0371421cfb0766c7f8bf0c23411e730717cd0d4924be0604109e` |
| Registered raw receipt | `89e6628cbecacced8ff6bb985986628a74a74a59d6fc84016b6b87d61af5cd3a` |
| Default raw receipt | `a7dd2f08a2f428fa66a1c05ea42786889ab368d1d0a624bdf54cb73a3c56373b` |
| Registered control CSV (original run) | `c787fcb35525f8554c8b5349159eb6f6a31fb4bd49f9fcf95130970f3448861e` |
| Default control CSV (original run) | `b0d60e80101b34ff163b85ef7547814e0403561b315f975eb38a98817b7eb84d` |

Archive: `hdl/library/starlink_pss_acquisition/evidence/balanced-identity-v1/`.
Its verified manifest covers both frozen source/vector/script sets, scopes,
raw receipts, Vivado logs, unit/mutation logs and stimuli. The scopes' git field
records the pre-commit base; all seven frozen RTL files and the actual bench
byte-match the tested source pin above. Reproduce with its simulation Tcl,
a new output directory, the immutable cursor-paired vector directory,175 and
optional `registered-scheduling`; unit command selects `test_balanced_identity.py`.

No synthesis/route has run for either held-phase-only or this comparator source.
The last −2.438 ns175 route belongs to the earlier unsplit input mux. Current
area, mapping, timing and replacement eligibility are unproven; all previous
CDC/external OOC interface caveats remain. No constraint change, clock relaxation,
receiver build, deployment or radio action. Stop for source/evidence review
before any physical trial.
