# Full production-map review and independent primary smoke

The original full production-map simulation passed, and its additive harness,
independent periodic oracle and complete evidence are now integrated on the
experimental primary branch. No runtime RTL, receiver profile, radio or PPU
configuration changed.

Integration pins: FW `205b7eb0b2258e16555fdb81315ceb235607bad9`, HDL
`c8ad25a7c0ad590dfc2c37eadb03d542e9f43dd2`. The HDL merge adds only four test/
runner files; the firmware merge adds the oracle, policy tests and reports.
The expected gitlink merge conflict was resolved to that explicit HDL merge,
not to a control-path experiment. Existing untracked primary HDL builds remain.

## Original full run reviewed

Original agent-owned88186 exited0 at05:12:16UTC with no restart. Parent read
the full report, terminal log, strict verifier and the bench's arithmetic,
score, publication, retained-read and partial-abort assertions. Parent independently
verified all103 file receipts, the portable archive SHA and104 safe unique
archive members, and replayed the strict terminal verifier against the actual
simulator log. All151 production-map policy tests passed again in1.17s.

The exact scope is1,280,000 admitted scores and all20,000 map words, one exact
excluded tail, continued source through retained reads/release and447 fresh
scores followed by a classified partial abort. One full production map passed;
a second full recovered production map was not run. The complete original
report and archives are retained in this repository:

- [Full report](../../docs/starlink-bank-production-map-full-20260910.md).
- [Prelaunch report](../../docs/starlink-bank-production-map-prelaunch-20260910.md).
- [Full archive](20260910-bank-production-map-full.tgz), SHA256
  `42d8401b36ab64c47a0a857563a5b0d27da44ab44b5258907a1333669eb5c920`.

## Independent primary actual-core smoke

Original parent-owned67376 exited0 at05:20:49UTC, without a retry. Command:

```text
env LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE \
 /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
 -source simulate_bank_production_map.tcl \
 -log /tmp/starlink-bank-route.I50MDJ/main-bank-production-map-smoke-v1.vivado.log \
 -journal /tmp/starlink-bank-route.I50MDJ/main-bank-production-map-smoke-v1.vivado.jou \
 -tclargs /tmp/starlink-bank-route.I50MDJ/main-bank-production-map-smoke-v1 \
 /tmp/starlink-bank-route.I50MDJ/periodic-map-oracle-independent-v1 smoke
```

Working directory: primary `hdl/library/starlink_pss_acquisition`.
The input oracle directory is the parent's earlier independent14-file numerical
regeneration, not a fresh golden derived from this simulation.

All61 frozen primary files byte-match the original full-run freeze. The runner's
aggregate signature changes with the ordering of absolute input paths even when
every frozen basename/payload matches; this run records
`98635d7fca5286a27a4027962abda0cc1de7dd635550c7352328b298f2a8dc4b`,
whereas the original full run retains its reviewed `b10e4f...` signature.
This is a source-byte comparison, not a second full simulation claim.

Two343x2 maps pass:686 admitted scores/map,687 visible scores/map with one
checked excluded tail,343 exact map words/map and354 continued source samples
during retention/read/release. A fresh447-score partial abort passes with
reason10 and historical generation2. Totals:1,821 exact visible scores,
1,819 admitted,686 returned map words,5,058 source presentations and three
terminal receipts. Full simulated duration343040ns. The strict postprocessor
passes after simulation closes.

Combined primary tests:352PASS in4.77s across production-map policy, native
paired policy, paired realtime PSMA stop policy and realtime probe-result tests.
The archived simulation includes all61 frozen inputs, compile/elaboration/
simulation logs, generated-wrapper identity, scope/runtime and original outer
log/journal. No proprietary C-model binaries or large waveforms are copied.

| Artifact | SHA256 |
| --- | --- |
| `20260910-bank-production-map-primary-smoke.tgz` | `a4e34585566d7a520ad4213b4bb37311d673bf00b639a6f5628518841c2c3e41` |
| Primary `scope.txt` | `3afc844670b6354feebe815159fe1ff8e1af95b5684a29f5492f299e032c0f01` |
| Primary `simulate.log` | `7f7e331f10250547086f3ea74f23237da916291efb0471c87de79e3cdb53e606` |

These checks establish bounded synthetic arithmetic/geometry/lifecycle behavior,
not RF detection accuracy, physical timing closure, live120ms deadlines or
high-rate native/pilot/IIO integration. The full15/30/60 deployment scope remains
in [the integration gates](../starlink-bank-owned-integration-gates-20260910.md).
