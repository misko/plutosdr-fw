# Starlink PSS 15 MS/s ARM acquisition checkpoint v1

Status: **PASS OFFLINE / DO NOT MERGE / RADIO UNTOUCHED**

This checkpoint implements the bounded processor-side policy after the
continuous 15 MS/s phase-map bridge. It does not connect the bridge to the RX
shell, assign an MMIO aperture, install a target executable, build a firmware
image, contact a radio, or establish PSS frame alignment.

## Implemented boundary

The C library accepts only the frozen `PSMA` ABI 1.0 contract: 20,000
one-sample phase bins, 64 frames per map, 16-bit map words, two immutable
banks, and capability word `0x1f`. Snapshot requests are generation-bracketed
and reject pending, concurrent, overrun, or saturated snapshot state. A map
copy reads exactly 20,000 zero-extended words and takes a second coherent
snapshot before release. A changed bank identity, fault counter, or bridge
command status leaves FPGA ownership retained for diagnosis.

Every successful copy retains its before/after hardware-health epochs.
Continuity between copies requires adjacent map generations, exactly
1,280,000 accepted-sample indexes between tile starts, unchanged nonsaturated
acquisition fault counters, and unchanged bridge read/release error counters.
This provides the `continuity_ok` input to the lock policy from checked
hardware state rather than assuming it in an application.

The candidate extractor keeps exactly three consecutive maps. It permits at
most seven strictly increasing drift hypotheses and freezes the production
bank at `[-12, -8, -4, 0, 4, 8, 12]` phase bins per 64-frame tile. That is
approximately `[-9.375, -6.25, -3.125, 0, 3.125, 6.25, 9.375]` ppm around a
20,000-sample frame. For each hypothesis it shifts and sums all three maps,
selects the largest score with the Python oracle's smallest-drift then
smallest-phase tie rule, and computes the same odd/even median, MAD,
peak-to-median ratio, robust z score, and period estimate.

The working allocation is fixed at approximately 320 kB:

| Buffer | Size |
|---|---:|
| Three 20,000-word `uint16_t` maps | 120,000 bytes |
| Two 20,000-word `uint32_t` scratch arrays | 160,000 bytes |
| One incoming immutable map | 40,000 bytes |

The state controller implements
`ACQUIRE -> CONFIRM -> LOCK -> TRACK -> HOLDOVER -> ACQUIRE`. It requires at
least two threshold-passing observations, checks circular phase and drift
consistency, uses exact generation/start-index continuity, allows a configured
number of holdover misses, and fails closed to acquisition on a metadata or
hardware-health discontinuity. `LOCK` is the one-step publication transition;
the next consistent observation enters `TRACK`.

## Offline verification

`run_starlink_pss15_arm_acquisition.sh` is the complete offline gate. It ran
without opening IIO, USB, a network-radio interface, serial console, DFU, or
flash and produced the frozen summary with SHA-256
`7ce4cb62daa63503b8a34270a330344036f3662da5be1cb4ff074eee02b87c6d`.

The native test compiles with GCC 15.2 under C11 `-Wall -Wextra -Werror
-Wpedantic`. It exercises two complete 20,000-word copies, bank retention on
metadata and fault-epoch failures, snapshot and ABI rejection, map-window
continuity, bounded drift selection, deterministic ties, finite and zero MAD,
unsafe geometry, and the complete lock-state path. The same binary passes
AddressSanitizer and UndefinedBehaviorSanitizer with leak detection enabled.

The library independently cross-compiles with the project Linaro GCC 7.3.1
toolchain as a 32-bit ARM EABI relocatable object. It is deliberately not
linked into the existing tracker controller because the phase-map bridge does
not yet have a routed shell address.

The Python differential suite contains 13 passing cases: twelve randomized
odd/even map geometries and one zero-MAD tie. Every C phase, drift, combined
score, median, peak-to-median ratio, robust z score, and frame-period estimate
matches `tests.starlink_oracle.acquisition.search_phase_map_drift`.

## Source and qualification boundary

The source is frozen at firmware commit
`b26ed7a685d9d994b89fa9159af751825835270b`, tagged
`starlink-rx-only-dnm-v1-source/firmware-pss15-arm-acquisition-v1` on
`codex/starlink-rx-only-do-not-merge`. It reuses unchanged HDL commit
`e2e1b87fccfb7efbeb3612e2a3b5a0fea919ba93`; therefore it introduces no new
component gitlink and needs no additional firmware-main gitlink denylist entry.
No PPU source changed.

The only reserved future RAM-validation radio remains serial
`104000bac4950008230026001b440a003a`. No radio was contacted, and all other
local radios remain free.

The next Stage-15 gate is to connect the already checkpointed IQ-to-phase-map
path and AXI bridge to the real one-RX shell, add a versioned MMIO aperture and
target packaging for this policy, and close a full linked-system route. Only
then can deterministic RAM-only validation measure map-copy/extraction latency
and exercise the state controller on the reserved radio. The 30 MS/s x2 and
60 MS/s x4 acquisition front ends remain subsequent independently qualified
stages.
