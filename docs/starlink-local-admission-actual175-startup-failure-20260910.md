# Local admission actual175 v2 — time-zero observer failure

The single corrected L1/R1B1O1/175 attempt **failed**, original handle14041 / process
exit1. The diagnostic scope correction worked and `run all` was reached, but the
first new guard comparison failed at time0fs, iteration1, phase0. No healthy block,
numerical event set or full-equivalence terminal completed. The original failed
22656 attempt remains unchanged and separately archived.

Owner: `hdl/library/starlink_pss_acquisition/build/local-admission-L1-175-actual-owned-v2`.
Original process start2026-09-10T11:28:49.030957UTC, end11:29:17.130980UTC,
28.0999s. Vivado's exit log line is11:29:07UTC; owner timing includes shutdown.
No restart, L0 run, WDB-query invocation or physical tool execution was performed.

Exact prepared-v3 manifest:
`ae2173b877d75fc6f97246e612415e9c33a1f9d0215a6e5b1d3eb49bf6ae2f22`.
Runner remains `f76090eba45113c44eff258fa1482198b663747787b76b14ce24a39bee7ebb98`.
Tested FW `ce6c57185a33d09904656dd570a6250e051efaef` /
HDL `e0e075d72711e27a866bdadebc1c14ef19c58326`.
The new owner script differs by exactly the four authorized substitutions and has
SHA `a8948955e31ee4ebfc39aa605b57e8407a079fefa5b9d3ebf9535c0bb5bfab99`.

All46 frozen source hashes and manifest match before/after. Original owner exit1,
launch_error=null, after_integrity_error=null, source_unchanged=true; runner
run_status1/after_status0; results.json absent. Generated IP source before/after
matches `a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.

## Observed evidence, not a waiver

Both exclusive closed diagnostic receipts and115 arithmetic /14 observer paths
were produced under the actual escaped parameterized root. This establishes
successful signal selection, not yet independent verification of saved histories.

The unmodified new observer reports:

```
phase=0 time=0
actual  = X0XxxxX0XxxxxXxxxxxxxxxxxxxxxxxxxxxxxxX
original= X0XxxxX0Xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
default = X0XxxxX0Xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
resetn=x start=x descriptor=xxxxxxxxxxxxxxxxxx
input_metadata=xxxxxxxxxxxxxxxxxx position=xxx
```

It terminates with LOCAL_GUARD_UNCONDITIONAL_STATE_OUTPUT_MISMATCH at0fs,
iteration1. The comparison is the observer's immediate pre-edge phase on
`always @(posedge clk or negedge clk)`. The bench declares clocks initialized to0;
an X→0 initialization transition can trigger that process before nested
combinational nets settle. This is a scheduling hypothesis from source and the
reported time/phase, **not proof that the difference is benign**. The current
hexadecimal diagnostic does not expose every bit of mixed-X nibbles. No mask,
delay, check removal, source correction or retry is authorized by this result.

Raw hashes:

- WDB `61b685f55940d89f1124d4fd4869c6f146e6a54207354f5ab1a15ba4c722177f`.
- simulate.log `6f8355e475bcc1aa417fc248720a34001913c412787b479d6430080e58f555cf`.
- observer inventory `72aedb62c9e36dc28e4f1cbcaf7b4882ef2f258709c226472e2e77cc5f5c00a1`.
- original outer.log `df35b65a7dbe73951124f3b5a2b18879970392be797bc3213609ff7ce50151f0`.

All original project, compiled elaboration files, waveform, exact sources,
command/exit and logs are archived unchanged. Next work is read-only diagnosis of
field differences/connectivity/event ordering. There is no qualified actual-core,
throughput, scorer-RTL, physical timing or RF result from this attempt.
