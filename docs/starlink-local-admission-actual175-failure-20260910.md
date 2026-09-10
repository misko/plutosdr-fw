# Local admission L1 actual175 — failed before bench advancement

The single authorized actual attempt **failed**, original handle22656 / process
exit1. It did not reach `run all`, a guard comparison, a healthy block, or any
numerical event. There is no arithmetic-equivalence, latency or physical result.

Original owner directory:
`hdl/library/starlink_pss_acquisition/build/local-admission-L1-175-actual-owned-v1`.
Start 2026-09-10T11:10:48.649453UTC, process end11:11:16.174700UTC, 27.525s.
The original Vivado log exit line is11:11:06UTC; the owner end includes process
shutdown. No restart or second attempt was made. L0 remains unexecuted.

Source was exact R1/B1/O1/L1/175 prepared-v2 manifest
`a84e723cb3de7b2c3382dbc88b89b6edc533d7493856540d1871d4ecd31831d5`,
runner `f76090eba45113c44eff258fa1482198b663747787b76b14ce24a39bee7ebb98`,
FW `5c479ff19740e473501d90353cd0c376bec20d15` /
HDL `e0e075d72711e27a866bdadebc1c14ef19c58326`. All45 frozen file hashes and the
manifest match before/after. Run receipt has run_status1/after_status0; results.json
is absent. The generated vendor wrapper before/after receipt remains equal.

## Exact failure and read-only diagnosis

Outer.log lines482–483 report `No object found for the given pattern` followed by
`LOCAL_GUARD_WAVE_PATH_MISSING actual_view`. New waveform setup tried the literal
unparameterized path:

```
/tb_starlink_pss_local_admission_actual/local_guard_observer/actual_view
```

The existing recursive arithmetic inventory successfully recorded115 paths whose
actual Xsim root is instead the escaped parameterized identifier:

```
/\tb_starlink_pss_local_admission_actual(FAST_MHZ=175,B=1,O=1,L=1) /
```

The hardcoded root therefore does not name the elaborated scope. The new observer
path setup stopped on its first lookup before the original `run all` command.
`simulate.log` contains only `Time resolution is 1 fs`; the downstream result
parser correctly rejected the missing FFT_BANK_OWNED_SLICE_PASS. Vivado's generic
“simulation ran for all” informational line does not override these facts.
No LOCAL_GUARD_UNCONDITIONAL_STATE_OUTPUT_MISMATCH occurred. No independent WDB
query or further simulator invocation was performed for this diagnosis.

The preparation's mock waveform test verified the assumed literal paths but did
not model Xsim's parameterized escaped top name; its121-test offline PASS remains
limited accordingly. The failing actual files, project, WDB, owner command/exit,
original sources, arithmetic inventory and all logs are preserved unchanged.

Proposed next correction, **not implemented here**: enumerate real objects as the
existing arithmetic diagnostic already does, identify exactly one of each required
observer/leaf suffix, and require all14 paths to share the actual top root tied to
the arithmetic inventory. Validate explicit profile-specific plain/escaped root
forms; preserve exact recorded strings rather than rewriting WDB paths. Keep all
155-bit comparisons, default/original shadows, forces, runtime and numerical
expectations unchanged. Any corrected preparation and later actual attempt need
separate source-specific review and authorization.
