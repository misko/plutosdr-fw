# Forward-return bank: functional proof and measured resource budget

DO NOT MERGE or deploy. Branch
`codex/starlink-rx-only-do-not-merge-forward-return-bank`.
HDL `b10eaac3246c023398284a915da0bdf2e32d5f68`;
FW implementation `a5bc7c561`, archive-curation follow-up `b0387b8eb`.

A new private 512x36 whole-block bank reserves storage before the real-time
FFT, captures independently of downstream READY, and replays only after a
separate qualified seal. Local ordinal/LAST/exponent/descriptor checks cannot
authorize replay on their own. Stalls hold the replay word; final consumption
returns ownership. Faults immediately fence replay and quarantine until reset.
The caller still owns input/status/vendor-event validation, final-fence
qualification, publication vetoes, epoch reset and a bounded job watchdog.

This component is **not wired into the receiver's control path yet**. All 22
existing runtime modules are unchanged. The actual-FFT bench adds a private
observer that cannot drive the reference DUT. The current receiver's failing
timing remains unresolved.

## Tests and actual FFT

1077 regression tests pass (116.92 s), including 31 component/source and 11
observer-evidence checks. Component tests cover 12 full blocks / 6144 words,
3108 stalled-valid cycles, one-word-per-clock unstalled replay, three reset
boundaries, 20 malformed/abort cases with fresh recovery, and nine rejected
unsafe mutations. Full-width block-start/descriptor values are held through
replay rather than recomputed from processing latency; this is not RF timing
accuracy evidence.

Both actual generated FFT observer campaigns pass:

| Campaign | Complete blocks | Checked replay words | Reservations | Seals | Stalls |
| --- | ---: | ---: | ---: | ---: | ---: |
| Main | 71 | 37689 | 109 | 98 | 15077 |
| Auxiliary | 73 | 37455 | 92 | 81 | 15008 |

Words include partial private replays subsequently cancelled by intentional
fault tests; these are not public detector measurements. All 64512 original
CSV rows remain exact, SHA256
`7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d`.
Original service remains 3663/3663/4929/11729/3663/3663 clocks. **This is the
old scheduler's service, not proof of the new buffered schedule.** Main/aux
runs took 213.77/186.30 s.

Failed preliminary checks are retained. A testbench hold snapshot was one bit
too narrow; a separate internal RAM-read-bound assertion was needed to reject
an extra-read mutation whose data was masked on final retirement. The initial
actual observer instance preceded the clock declaration, implicitly redeclaring
the clock and causing both runs to hit the deadline. The corrected observer
follows declarations and changes its private READY on the opposite edge.
No original stimulus or bank RTL was changed to obtain the passes.

## Standalone physical result — still not timing closed

Vivado 2022.2 / xc7z010clg400-1 / 5.714 ns clock:

- One RAMB18, SDP 36-bit writer B; 75 LUT, 111 FF, zero DSP.
- 154/154 nets routed, zero routing errors.
- Capture-ready and RAM write enable/address controls have no combinational
  dependency on downstream READY, verified in the routed netlist.
- WNS **-0.181 ns**, TNS **-7.073 ns**, **59/167 setup endpoints failing**.
- Hold +0.167 ns and pulse +2.357 ns pass.
- 197 input / 127 output ports remain unqualified by the standalone recipe.

Worst internal path runs from descriptor bit 3 through identity/fault checking
to the write-count enable: twelve levels (six CARRY4), 5.606 ns data delay.
The standalone result must not be compared as if it were the full subsystem's
WNS. It demonstrates a small memory/control footprint, not integrated closure.

## Next implementation and deployment gates

Preserve this measured source. Next remove wide identity/fault qualification
from private capture progress, or bound its comparator depth, while retaining
same-edge fault fences and quarantine. Then wire the forward guard to local
bank capacity and the kernel/product stage to sealed replay. Inverse admission
must await the actual qualified product bank; a guard completion alone is not
ownership return. Re-prove caller contracts for this new wiring rather than
reusing old parallel-READY equivalence as authority.

Measure the entire new capture/seal/replay/product-publication schedule under
continuous arrivals and stalls before routing the actual FFT plus buffers.
The estimate 3663+512≈4175 clocks versus 5215 available remains unproven.
Check total receiver RAM/control use; a standalone one-RAMB18 result does not
prove whole-device fit. Preserve native 60 MS/s fine search and independent
2.5 MS/s CI16 IIO throughout.

Full receiver timing/CDC/real clocks, 60 MS/s RX calibration, sustained IIO over
Ethernet, blind GLRT comparison, 120 ms dwells and 300 s scans remain release
gates. Use pinned PPU/rollback on .18 first, then .17 Ethernet-only. No radios
accessed, no PPU/main changes, primary HDL pointer unchanged. .14/.20/.21 excluded.

## Evidence

[Verified archive](20260911-forward-return-bank-evidence.tgz),
[read-back receipt](20260911-forward-return-bank-evidence.json):
22,669,501 bytes / 6723 members, SHA256
`e420f9ad34a18b724dd001d1692e94570e233657b4b29546bb34dc4702ea9b3b`.
Contains actual logs/CSV, frozen old/new observer sources, component/regression
tests, bank synthesis/routed checkpoints, complete write-port checks and
reports. Identical vendor VHDL is stored once. The omission inventory hashes
redundant historical regression CSV/DCP copies, whose raw files remain in RAM.

An initial uncurated archive exhausted disk space; that incomplete 180 MB file
was moved intact to `failed-archive-v1.tgz.partial` under the raw root. It is not
used as evidence or committed. The curated replacement was built and fully
read-back verified in RAM, then copied byte-identically to this report folder.
Three clean inactive tracked report checkouts were made sparse; their contents
remain in Git. No raw tests, sources or reports were deleted.

Raw root: `/dev/shm/starlink-forward-return.FEyGL1Bw`.
Prepared-v2 SHA: `947c2e9fe7a1b8a0acf449fdf32a69cceadef84a3e390a33c5d713bbf3d37824`.
Bank RTL SHA: `3bdb52c073d32dbb61032239778a6379f64712342ea5d876e90066e674e7f7d3`.
Standalone DCP SHA: `d6a093f490c167f2a3f8dea9fc61c848db34ed549efb05bbf18dc7c3762f4c33`.
[Previous scalar-fault result](20260911-scalar-fault-sources-actual-route.md).
