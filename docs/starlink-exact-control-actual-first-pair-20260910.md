# First exact-control actual pair: both fail, cause not yet identified

The two authorized real-core175MHz runs both terminate with exit1 at the
new whole-island observer, before any original terminal or extra-epoch
receipt. No retry, other mode, RTL change or physical run was performed.
Measured source: FW613b14e673a2cb4182f24bded113f1093b0258c6 /
HDL027a903f7dcbeec5afce496f3be428acd7e2abff; helpersd5cc9f28 and runtimeae50
unchanged. Both use extras1/QUICK0 and two threads in Vivado2022.2.

| Case | Original handle / exit | First failure time, fs | Wall / CPU user |
|---|---|---|---|
|r0-d0-s0 baseline|60442 /1|1198594347644|250.53s /244.82s|
|r1-d1-s1 combined|8914 /1|1200640062032|250.88s /245.85s|

Both journals begin06:35:58UTC and Vivado exits06:39:58UTC; `/usr/bin/time`
also includes program startup. The exact first assertion is
`Fatal: EXACT_ACTUAL_PUBLIC_REASON_OWNERSHIP_MISMATCH actual=0 old=1`,
observer line40. Here0/1 are the full concatenation's equality result and
expected true, NOT the differing field values. Both failures occur in
epoch11, the original missing-forward-status test: mask status, force an
apparent product-bank candidate, then hold the final return while injecting
status5 and releasing the force. No held-final-ready witness has yet been
counted. This localizes the observation but does not establish its cause.
Default-mode failure alone does not prove a harness defect.

Partial candidate/reference main CSVs are byte-identical within each run:

- Baseline209755 lines, both
  `dd695cd5afb7da1df04e2b6ec731e18f42dbe7c361b1c518f1a1d126e216ab3c`.
- Combined210113 lines, both
  `d81ec8839d14b29cfab50a348231cda6fab3df853ff71d38b06612efbc94daa8`.

These are incomplete traces, not the required historical full hashes.
No EXACT_CONTROL_ACTUAL_PASS, original suite PASS, or extra PASS exists.
The terminal parser/full-CSV gate was not reached. All frozen inventories
passed before launch and again after failure; original RTL and settings
remain untouched. There are27 warnings per run:16VRFC10-8426 output-port
initialization,8VRFC10-3380 predeclaration,1VRFC10-3532 glbl generic override,
1IP_Flow19-4832 and1Vivado12-13277. Raw messages are retained without waiver.

## Read-only WDB diagnosis and its limit

Separate read-only Vivado handle2352 exited0 after opening the saved WDBs;
it did not create a live simulation or rerun time. `get_value_database`
at each first-failure time exposes only23/217 candidate operands and0/217
reference operands: **zero paired fields are recoverable**. Names exist for
unlogged internal scopes, but historical values return `<Blank>`.
The default simulation Tcl used only `add_wave /`. Both WDB hashes remain
unchanged after inspection; command-discovery/escaping errors are retained.

Recoverable candidate counters below are partial observations, not receipts:

| Counter | Baseline | Combined |
|---|---:|---:|
|successful whole-field checks|419508|420224|
|active checks|318945|319125|
|next-identity consumptions|36|36|
|private scratch differences|0|33|
|active final-fault edges|0|0|
|owned-stall edges|62414|62589|
|reset-owned edges|3|3|

The required next observation is the exact named mismatching operands at
the same existing failure edge, plus both benches' injected status, clock,
epoch and test-kind values. This must retain the comparison,2ps sampling,
fatal, original stimulus and every numerical/CSV gate. Observation-only
diagnostic preparation is separately authorized; no diagnostic actual run
is yet approved. No contract relaxation or candidate defect is inferred.

Archive: `hdl/library/starlink_pss_acquisition/evidence/exact-control-actual-first-pair-v1/`.
It preserves both full frozen source sets/settings, original launch/tool/
simulation logs and timings, after-hash checks, compressed partial CSVs and
WDBs, and the full read-only inspection journal/log. Raw projects remain at
`/tmp/starlink-completed-input.5EaJuD/exact-control-actual-matrix-v3/` in the
two case directories. WDB SHA256: baseline
`f8028f12daa9a43fe5855ae1a51af750642f8241b7f0db4f93751cd6c207262f`,
combined `7973536a620af69175833c42f1672a56dcb8dbcf8dc052b003aa0cc85b0712d9`.
