# Local observer waveform discovery — offline correction only

The narrow correction passed **143 tests / 7.07 s**, Ruff PASS, original handle85000
exit0 at `/tmp/starlink-local-wave-fix-offline-v1.GA0kgd`. No vendor simulator,
WDB query or physical tool was invoked. The original failed22656 attempt remains
unchanged; it never reached `run all` because of a hardcoded diagnostic scope name.

Code pins: FW `6951006e63997f63f6f3bf0cd73cb4e5cea66b65` /
HDL `e0e075d72711e27a866bdadebc1c14ef19c58326`.

Only the additive diagnostic discovery and receipt verification changed. The
existing 155-bit observer, all compiled sources, runtime, old/new bench stimulus,
119-bit product checks, numerical vectors, clocks/generics and launch runner are
byte-identical to the failed v2 preparation. A policy test enforces this exact
frozen-source delta: helper, policy and diagnostic Tcl changed; one read-only
archived arithmetic signal inventory was added. No comparison or fault mask changed.

The new Tcl enumerates existing objects recursively and requires exactly one of
each14 observer leaf names. Every accepted path must be the direct
`<root>/local_guard_observer/<leaf>` and share the original arithmetic inventory's
root. Only the exact plain top name or profile-specific escaped parameterized name
is allowed. Paths retain every original backslash and whitespace; there is no
normalization or substitution of recorded WDB identifiers. The arithmetic Tcl,
its115-object collection and final original `run all` remain unchanged.

The added real failure fixture has SHA
`f2cc4bee468b97cec08e8f71417150cf16e56841df43741f9266b6365132ace6`,
the complete original115-path inventory from attempt22656. Its actual escaped
root is `/\tb_starlink_pss_local_admission_actual(FAST_MHZ=175,B=1,O=1,L=1) /`.
The tests use this literal fixture and explicitly derived plain/L0 control forms,
not claim those controls were observed in a vendor run.

Mock execution of the complete diagnostic Tcl reaches an unchanged `run all` trap
for L0/L1 and plain/escaped roots without simulating anything. Duplicate/missing
leaves, mixed roots, wrong profile, mismatched arithmetic root, nested observer,
path injection and unknown leaf are rejected before receipt or run. Matching
Python verifier tests reject the same cases. Existing source alias, inventory,
instance binding, guard corruption, original collector numerical/fault checks
and launch/post-integrity rejection tests remain passing.

New source-only bundles under `hdl/library/starlink_pss_acquisition/build`:

- `local-admission-actual-R1B1O1-L0-175-prepared-v3`: manifest
  `58ec6bcf4a2e395ebf344ac7999c5f65db269677ecbc92f38c4bb4875445318a`.
- `local-admission-actual-R1B1O1-L1-175-prepared-v3`: manifest
  `ae2173b877d75fc6f97246e612415e9c33a1f9d0215a6e5b1d3eb49bf6ae2f22`.

Each has46 frozen files,19 compiled sources and8 runtime modules. L1 diagnostic
SHA is `260e9dc61259ca3c6901fc46ad0fbaf9994943f2c30e2fa1f8041d15960865c7`;
runner remains `f76090eba45113c44eff258fa1482198b663747787b76b14ce24a39bee7ebb98`.
Neither bundle has a project or launch receipt at this preparation gate.

The smallest proposed next evaluation remains one separately authorized L1/175
actual run. All11 original terminals,76 core-job timing records, complete prior
R1/B1/O1 CSV, forward/product/inverse and oracle-only scores, full guard comparisons
and recorded WDB-history inspection remain required. No L0 actual, D/S/CDC union,
canonical promotion or physical result is included in this correction.
