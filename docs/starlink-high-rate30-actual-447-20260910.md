# Actual healthy30-upper/175MHz paired447x2 result

PASS: original handle57213, launcher0, Tcl0, post-integrity0. One actual run
used frozen FW6a99d1d538889c79630758ac86c4493ea254640d /
HDL446a8617adbabcce5122705e528dc997ff06d263 with no runtime/test/source changes,
retry, tail extension or alternate profile. Parent independently reverified
the frozen inputs and numerical result.

Run: `/tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-447-v2`.
95-source signature:
`413f9cd065da934d258750b30075d5e9c75ff16efd9484a51222ca0b3043cb31`.
Bundle SHA256:
`2d410bc8a7984425751a527725e8f43c8406596b23f610e904199d1524863da5`.
All358 frozen inputs passed post-run verification.

Exact observations:12303 original source/CDC beats including2 disabled-prime,
8205 original and4096 fixed-tail samples;7250 enabled raw/3618 canonical;
1536 actual175-clock forward input/output/product/inverse-input words;
1024 slow inverse-output words;894 energy/normalized-ratio/score words,
894 map admissions and447 public map reads. The third inverse input was
consumed but its slow output was not observed: no seven-job/completion claim.

Native:260 ORIGINAL raw captures,129 raw/121 qualified tuples,26 packet words
read twice (52 reads), exact independent release. PIL1:3617 accepted/mixed,
1808 halfband,602 all outputs (90 unsupported),512 delivered/2048 exact bytes.
Every observed prefix remained checked against the original51 frozen goldens.

STOP at source4946/canonical2464/pilot319 saw native capture complete and
correlator busy. The complete map remained owned through native public release
at source8991; map release completed at9000; source continued to12303.
Overlap witnesses:273 actual FFT-consumption/native-capture fast beats,
6433 native-compute/coarse+pilot clocks,13219 native-compute clocks after STOP,
43723 fast-clock bank-quiescence observations. No health failure was observed.

Native admission:index17179869201, capture_start17179870128, lead926,
deadline17179869408. Publication19910 cycles after capture; public read/release
20700; max AXI8, within unchanged24000/28000-cycle bounds. The prior Icarus
publication measurement was19911: this one-cycle difference is preserved.

Endpoint453870ns; xsim CPU18.960s, peak memory186440KB on gauss/x86_64.
This proves this bounded static-known-center numerical/lifetime case, not RF
accuracy, causal scheduling, ARM/bus capacity, DMA/IIO,120ms dwell, production
20k×64 geometry, physical closure,60MS/s or lower-edge admission.

The working invocation (from the isolated HDL acquisition directory) was:

```sh
env LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE \
  /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
  -source /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate-paired/hdl/library/starlink_pss_acquisition/simulate_high_rate_bank_native_paired.tcl \
  -log /tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-447-v2.vivado.log \
  -journal /tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-447-v2.vivado.jou \
  -tclargs /tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-447-v2 \
  /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate-paired/build/high-rate-harness-prelaunch-v1 \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python
```

The v1 invocation lacked that loader path and failed before Tcl/project creation
with missing libtinfo.so.5 despite launcher0. Its exact command/stderr are
preserved, SHA223087f01f9fb9b68c75451fddeba62939c0b0adc44293e543baa119f26a59eb.
The v2 runner enforced maxThreads2 and sanitized only independent Python
subprocess environments. No source or installed-library change was needed.

Full636-file raw run remains intact (47MB, including4.6MB default WDB);
`artifact-inventory.sha256` SHA
`6fc261be4095eb3ba27cd7f3c9e8f1787103134675fa4365331f1175729f1d7a`.
Portable source/log/numerical proof is
`reports/experiments/20260910-high-rate30-bank175-447-actual-v2.tgz` with its
adjacent JSON archive receipt. It includes the frozen input closure, raw129
tuples,512 pilot bytes, complete simulation/compile/elaboration logs, generated
actual FFT wrapper and v1 failure; generated project executables/WDB are not
duplicated. No raw evidence was deleted.
