# Healthy paired60: one authorized actual-IP result

PASS: original process5432 exited0; the bench and unchanged frozen result
verifier both passed. `run_status.txt` reports `run_tcl_exit=0 integrity_exit=0`.
The original69 numerical files, runtime, source, recipe and service bounds were
not changed; there were no retries. Root independently reran the frozen result
CLI from `/`, checked both input bundles and generated-wrapper identity, and
confirmed the saved terminal receipt.

Launch FW `b47c355b08cf66af126f173093cf90b4928fca99`, HDL
`88195cd9029a0c66f642fe21045ff70053fc46de`. The approved runtime remains
`f16dc564`; this result does not promote its PSMA1.8 host/receiver ABI support.
Frozen bundle SHA256:
`b5f7d48a96217691d7a034634d3bdc7006e489066e571d93b00ce2ed5f741714`.
The108-source signature remains
`26f33d8727828eabd56d24466984168be3bdc52fc5e0166ba8ffe94f0e89b8e8`.
Runner SHA256:
`c8233d7200a7dbbefe1ac5644350101ebc70784151095cfb3166e290cbaa471d`.

## Measured evidence

| Check | Actual result |
| --- | --- |
| Source | Two separately logged disabled primes plus16,423 original raw samples,16,425 exact CDC deliveries; no added tail |
| Startup |3,111 original raw →1,549 intermediate30 →768 canonical; declared2,000-control-cycle drain/pause outside continuous segment |
| Continuous original segment | All13,312 samples `[34359738322,34359751634)` at successive true60 source edges; first rise102293762575fs, last rise324143753701fs, source-off324152087034fs |
| Public admission | PSMA1.8/caps0x7ff, exact source60/x4 filter/kernel/Eh; native1.3/264-tap geometry; PIL1 source60/output2.5/stride24 |
| Actual enabled cascade prefix |14,518 raw accepted;7,251 stage30 outputs,7,250 accepted by stage2;3,618 canonical outputs; both per-edge enabled/phase/pipeline/count ledgers passed |
| FFT words checked |1,536 each forward input, forward output, product, inverse input;1,024 visible inverse output words; every visible word/index/last/BFP exponent exact |
| Coarse scores/map |894 exact energy/normalization/score tuples;894 visible and894 map-admitted, zero visible tail;447 exact retained-map reads |
| Pilot |3,617 accepted/mixed,1,808 halfband,602 final-filter outputs including90 unsupported;512 exact retained/exported words and2,048 bytes; coherent PIL1 snapshot |
| Native admission | Actual raw index34359738591, lead1664; triggercycle10625, handshake10678,53 cycles within256 limit |
| Native capture/results |520 original-raw captures, all257 integer raw tuples/powers,241 qualified; two26-word packet reads,52 total; request60000520/generation60000001 |
| Full lifetime | Publication at raw249 with8 remaining unqualified tuples; release at raw252; all257 drained and engine/bridge idle later |
| Actual overlap |245 FFT-clock core input handshakes while native capture active;5,671 control cycles native compute with coarse work and pilot enabled;67,405 compute cycles after coarse STOP |
| Retention/quiescence | Map retained through independent native result release; native/map releases both after all16,425 source beats;119,038 bank-quiescent FFT cycles;256 final quiet control cycles |

The actual bounded prefix matters: pilot auto-stop closed the conditioner, and
bank STOP canceled unpromised downstream work. This is NOT4,096 canonical
outputs or seven completed FFT jobs. All visible/provisional prefixes were
compared; no numeric check was waived for cancellation. The third inverse
input block was transferred, but only two inverse output blocks became visible.

The true60 source oscillator first rose at10.433333ns and first fell at
18.766666ns, with quantized16.666666ns period. The ideal175 FFT oscillator first
rose4.157143ns, first fell7.014286ns, period5.714286ns. Final inventories were
53,745 source rises (34,296 after source-off) and156,758 FFT rises. Source strobe
remained uninterrupted for the declared13,312 post-preroll samples, through
native capture; the earlier startup pause prevents an all16,423-wall-clock-
continuous claim. No actual MMCM or physical clock-quality claim is made.

Native service coordinates, in100MHz control cycles:

| Event | Absolute cycle | Cycles after capture-end |
| --- | ---: | ---: |
| Capture complete |14,318 |0 |
| Finite source off, compute still busy |32,415 |18,097 |
| Result publication |86,814 |72,496 ≤84,000 |
| Independent public result release |87,604 |73,286 ≤88,000 |
| Complete257-tuple drain/idle |88,959 |74,641 ≤84,000 |
| Final no-stale observation |89,320..89,576 |256-cycle interval |

Maximum tuple hold was11 cycles versus16 allowed; maximum AXI transaction was
8 cycles versus24; native readout used105 transactions versus140. Compute
continued56,544 control cycles after source-off. The source clock kept running.
The public low/high current-index read exactly matched its captured64-bit
witness34359738559, with capture lag2 and return lag9 (bounds2/31), returning
12 control cycles after capture (bound48). The actual command window and lead
bounds were unchanged. Native packet visit60000052 remains external fixture
context, not a field in the26-word native packet.

## Provenance and retained artifacts

Raw run, unchanged:
`/tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-447-v1`.
Exclusive ownership/audit directory:
`/tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-447-v1-owner`.
Original handle5432, initial chunk9f85da, terminal chunke58c18/exit0.
Vivado exited2026-09-10 11:39:18 UTC. Vendor simulation reported37s elapsed;
`launch_simulation` reported50s. These are host wall-clock observations on
`gauss`, not Zynq execution throughput or physical timing.

`project/high_rate60_bank_native_paired.sim/sim_1/behav/xsim/simulate.log`
contains exactly521 paired and60 native markers, including complete terminal,
STOP/retention, clock, continuous-source, budget and all512 pilot/52 packet
word receipts. Its native raw/capture/source/hold files retain every claimed
tuple and original index. `terminal_receipt.json` equals the independently
re-executed frozen CLI output. No failure/warning text is present in this
simulator result log. Ordinary Wavedata array-display warnings are retained
unaltered in the external Vivado console log; they are not simulator receipts.

`post-audit.json` rehashes all544 raw-run files (64,345,759 bytes), both external
and copied250-file input inventories, all108 live sources, every exported
simulator memory, and external log/journal. Nothing from the64MB original run
was removed. The generated wrapper's recorded pre-simulation SHA and final
SHA both equal
`a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.
Other generated-IP artifact hashes are recorded as post-run inventory, not
misrepresented as pre-run measurements.

Portable source/numeric/actual-receipt proof is
`reports/experiments/20260910-high-rate60-paired-actual-v1.tgz`, with adjacent
JSON safe-member/hash/length receipts and archive SHA. It retains the complete
frozen input bundle, actual source/capture/raw/hold/pilot outputs, simulator and
vendor logs, generated wrapper/configuration, full544-file inventory, owner
command and post-audit. Generated project libraries, compiled executable and
19MB WDB remain in the original run and are inventoried, not duplicated in the
compact archive. Packaging tools are receipt handling, not DUT source changes.

## Exact one-run invocation

All new run, owner, external log and journal paths were checked absent before
the exclusive owner directory was created. Working directory was that owner
directory. The accepted invocation was:

```sh
env LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE \
  /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
  -source /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/build/high-rate60-harness-prelaunch-v1/source_snapshot/hdl/library/starlink_pss_acquisition/simulate_high_rate60_bank_native_paired.tcl \
  -log /tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-447-v1.vivado.log \
  -journal /tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-447-v1.vivado.jou \
  -tclargs /tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-447-v1 \
  /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/build/high-rate60-harness-prelaunch-v1 \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python \
  b5f7d48a96217691d7a034634d3bdc7006e489066e571d93b00ce2ed5f741714
```

The frozen runner set2 threads and sanitized PYTHONHOME/PYTHONPATH/
LD_LIBRARY_PATH only in independent Python children, retaining Vivado's SuSE
library path. All pre/post input checks passed, without changing the runner.

Scope remains one static-known-center healthy447x2 digital composition with
ideal clocks and three independent direct AXI masters. This does not establish
causal coarse-to-native commands,750Hz detection, RF/timing accuracy, a full
20k×64 map,120ms scanner visits, shared-host service, DMA/IIO, physical60 timing
or receiver deployment. No radio, PPU, profile, runtime or physical changes were
made; no additional actual run or promotion is implied.
