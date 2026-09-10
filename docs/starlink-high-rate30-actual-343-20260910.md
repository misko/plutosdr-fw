# Actual 30-upper bank175 / native132 / PIL1: healthy343 PASS

The one authorized healthy343 run completed with launcher exit0, bench
PASS, frozen context-specific result verification PASS and post-run source
integrity exit0. Parent independently read the receipts and reran the
frozen result verifier successfully. No retries, tail extensions or source
changes occurred. This is behavioral actual FFT evidence, not physical/RF,
causal handoff, driver, DMA/IIO or production-map qualification.

Tested FW `f9c595998ea78fd4207e7d688edaf4c71954162e`, HDL
`529dc8e8d33afc237c7b26f8969ec32fa97cdbdd`; original handle69687 is terminal.
Source signature `b9d4d306fd9665133e36dc21e24125bce9ac7a6b3b34ed335b45fd5e2ba9ab09`.
Bundle SHA `bbec5b49d80caf3ec50b6d595e33e7cf62d4ca18e665caa1573099e90ad99bd7`.

Run directory:
`/tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-343-v1`.
Simulation artifacts are under
`project/high_rate_bank_native_case.sim/sim_1/behav/xsim`.
The exact invocation, from the isolated HDL acquisition library, was:

```sh
env LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE \
 /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
 -source /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate-paired/hdl/library/starlink_pss_acquisition/simulate_high_rate_bank_native_cases.tcl \
 -log /tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-343-v1.vivado.log \
 -journal /tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-343-v1.vivado.jou \
 -tclargs /tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-343-v1 \
 /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate-paired/build/high-rate-cases-healthy343-prelaunch-v1 \
 /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python
```

All output/log/journal paths were checked absent. Runner fixed two threads,
Vivado2022.2 and ideal independent30/100/175 clocks; generated real FFT
helper/arithmetic/kernel/oracles were unchanged. Vendor IP synthesis-target
file generation is not a synthesis/place/route run.

| Actual receipt | Result |
| --- | --- |
| Selected / visible / map words | 686 / 687 / 343 |
| Selection residue / visible tail | 239 / 1; tail numerically checked, not admitted |
| Forward input / forward / product | 1536 / 1024 / 1024 exact words |
| Inverse input / inverse output | 1024 / 1024 exact words |
| Score preparation / ratio / visible | 690 / 689 / 687 exact witnesses |
| Source / CDC / enabled raw / canonical | 12303 / 12303 / 7250 / 3618 |
| Pilot accepted / mixed / half / all | 3617 / 3617 / 1808 / 602 |
| Selected pilot outputs | 512 exact CI16 outputs / 2048 bytes |
| Native capture / raw / qualified | 260 / 129 / 121 |
| Native packet / reads | 26 words / two complete reads |
| Native engine / postcapture release | 19910 / 20700 clocks; limits24000/28000 |
| Maximum public AXI transaction | 8 clocks; limit24 |
| Native/FFT capture overlap | 273 observed source-clock events |
| Native compute / coarse / pilot overlap | 5393 control clocks |
| Native compute after coarse STOP | 14259 control clocks |
| Bank-only quiet after safe end | 45543 fast clocks |

At STOP, visible687/admitted686, source4634/canonical2308/pilot293,
native capture260 and native compute still busy. All343 map words were
read and the map stayed retained through independent native result release
at source8991; public map release completed at source9000. Source remained
continuous to12303. No tail score entered the map; complete provisional
prefixes of the score pipeline were still numerically checked. Actual1024
slow inverse outputs exceeded the separately frozen geometry minimum816;
this does not retrospectively change that bound or imply third-job output.

The native admission was index17179869201, capture start17179870128,
lead926, deadline17179869408. Capture ended at control cycle13182,
publication33092, public release33882. Static known-center injection of a
public command remains distinct from a causal coarse-derived candidate.
PIL1 selected first/last canonical indexes8589934350/8589937416, dropped90
unsupported prefix outputs and auto-stopped normally; every delivered word
and coherent snapshot was checked. Conditioner closure means3618 canonical
outputs, not an all4096 or allseven-FFT-job claim.

Terminal simulated time453870ns. Vendor simulation kernel reports18.360s
CPU and186440KB peak on this x86_64 host; it is not Zynq throughput or a
live120ms dwell deadline. The complete run, compile/elaborate/simulate logs,
raw129 tuple records, pilot binary, generated FFT wrapper and source closure
remain retained. `artifact-inventory.sha256` covers every raw-run file before
the two inventory receipts themselves; `artifact-summary.json` includes
those counts, hashes, exact result, host and original handle. The portable
archive/adjacent JSON in reports/experiments preserves the full frozen
inputs and numerical/log proof without duplicating generated libraries,
executables or WDB. No original file was removed.

Parent reviewed this outcome and authorized one subsequent actual late447
run from its separate frozen bundle; this report makes no claim about that
not-yet-executed run. The offline late probe and healthy343 actual evidence
must not be relabeled as a successful paired late447 integration.
