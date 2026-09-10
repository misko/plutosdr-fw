# Operand physical preparation: isolated Icarus environment correction

The authorized correction passes **60 offline tests in 2.84 s**: 31 physical
runner-policy tests plus 29 unchanged operand-wrapper tests. Ruff passes.
No physical retry was launched. Both original Vivado failures and their
source/log archive remain unchanged in FW
`83d17873e7bb6247e4560d64f89f46f9171eac1f`.

HDL preparation commit: `f7345ab655a21374f46d2bda89854f40295fca24`.
The complete runner diff from reviewed `7d4efdb3` is exactly two substitutions:

```text
exec iverilog ...  ->  exec env -u LD_LIBRARY_PATH iverilog ...
exec vvp ...       ->  exec env -u LD_LIBRARY_PATH vvp ...
```

Only these two system-tool children omit the inherited library search path.
The Vivado process environment, other subprocess environments, all arguments,
actual hierarchy assertions, strict one-line parameter marker, nonzero-exit
handling, log retention, source guards, flow and constraints are untouched.
An inverse-diff test removes these two prefixes and requires every remaining
runner byte to equal the earlier reviewed source. Core, wrapper, XDC and
parameter-probe bytes are unchanged.

## Executed environment and rejection checks

Two new actual-subprocess tests run options 0 and 1 under a Tcl parent with
LD_LIBRARY_PATH explicitly set to
`/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/Ubuntu`. Temporary executable shims record
only the child library-path state, then execute the real Icarus compiler and
simulator unchanged. Both children record `UNSET`; both parents retain the
exact original path before and after. Both real probes produce the required
exact parameter line, and both stop at the deliberate synthesis stub fence.
No actual Vivado process runs in these tests.

The original 28 policy tests continue to pass, including all eleven malformed,
duplicate, incorrect-parameter and trailing-failure receipts; nonzero exit
despite a correct marker; real fatal invalid-REGISTER and wrong-instantiated-
width probes; complete source inventory rejection; version/selection guards;
nonoverwrite; and relative output paths. The synthetic probe interceptor now
matches the exact sanitized command prefix, so these rejection tests still
exercise the same runner admission boundary. The new environment tests and
inverse-diff check bring the policy total to 31. No new failed attempt occurred
in this correction stage.

Unique raw directory:
`hdl/library/starlink_pss_acquisition/build/operand-environment-preparation-v1`.
Sibling `operand-environment-preparation-v1.outer.log` and the policy XML are
retained. Four valid preflights (ordinary and contaminated-parent, both arms)
have identical complete six-file pre/post snapshots.

## Frozen identities

| Frozen input | SHA256 |
| --- | --- |
| `measure_spectrum_operand_boundary.tcl` | `a3a733013e03e5bb60c8aeeb6ac029ef88136f2d407543c5a19368facc1d57d4` |
| `test_starlink_spectrum_operand_physical_policy.py` | `20b609a5f61f0bcfe7ab59329e8aa2d51ad987c5cb40b4337da6189ad91c91b8` |
| `starlink_pss_spectrum_product.v` | `4f9046d0efc395d68caa9b63911fcf5c18ab335b1f2707ad19d3794e0cc2329b` |
| `starlink_pss_spectrum_product_operand_register.v` | `dfb04b76e5ba9069565a8671794a365adcd2d516013d4f588eda8581f037b69d` |
| `starlink_pss_spectrum_operand_register_ooc.xdc` | `5ec96ae2f5a6e4b074a1c0ee2305f9fa7bb3d1a859e53f864789049d76a75ed9` |
| `tb_starlink_spectrum_operand_parameters.sv` | `1bd5698740bb9c36df67260093cf20e67863d3416256ed3ea6ac67053efd4fc6` |

Archive: `reports/experiments/20260910-operand-environment-preparation-evidence.tgz`;
SHA256 `19bea65015daa7e7f0c2528b83da70ec75030e3011f58a9436a76b60cdb9a533`;
667,063 bytes, 372 safe unique regular files, all member hashes verified.
`20260910-operand-environment-preparation-results.json` lists every artifact
hash, source identity and environment witness. Generated executables are
omitted; source, inputs, shims, environment traces and test logs are retained.
Installed tool binaries and the whole host environment are not archived.

This repairs a demonstrated subprocess dependency conflict, not RTL or
timing. DSP register inference, resources, setup/hold and route status still
have no successful physical measurement. A source-specific physical retry
requires separate approval and new output directories. Bank integration,
fault-latency qualification, actual FFT, receiver/radio/PPU work and full
coarse/native/pilot deployment remain outside this preparation.
