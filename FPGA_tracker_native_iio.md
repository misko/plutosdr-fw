# FPGA tracker native-IIO completion record

Status: 30 and 60 MS/s native result transport and cabled fine timing complete;
live-LNB 30 MS/s coarse PSS acquisition complete. Experimental firmware:
**DO NOT MERGE INTO FIRMWARE MAIN**.

This append-only record supplements the historically sealed
`FPGA_tracker.md` and `FPGA_tracker_60MS.md` files. It does not alter or weaken
their 15/30/60 MS/s gate definitions.

Authorized receiver: `104000bac4950008230026001b440a003a` at
`192.168.1.17`; its USB gadget is absent at the outdoor location.

Cabled transmitter: `1040007c4a94000211000b009186843ef2` TX1 at topology
`3-11`. It was used only for the historical 30 dB attenuated cabled sections;
it was not connected or opened for the outdoor live campaigns. Later sections
record the separately authorized persistent experimental image on `.17`.

## Native transport result

The `starlink-pss-iio-v5-dnm` RAM image uses two dedicated IIO devices:

- `starlink-pss-map` exports each 20,000-bin coarse map as 200 zero-padded
  256-byte scans (`le:U32/32X64>>0`, 59 logical words);
- `starlink-pss-track` exports each 26-word fine result as one zero-padded
  128-byte scan (`le:U32/32X32>>0`).

At 60 MS/s, map start indexes remain in canonical 15 MS/s units. Adjacent maps
advance by 1,280,000 canonical samples, or 5,120,000 source samples. PPU
multiplies a coarse candidate index by four before scheduling the full-rate
tracker.

Fresh-epoch USB validation received three maps (600 chunks, 153,600 bytes) in
0.279 seconds and 16 fine packets (2,048 bytes) in 0.223 seconds. Generations,
start indexes, request IDs, and scheduled centers were continuous, and every
map/tracker validation, push, and hardware-fault field remained zero.

A fresh Ethernet context at `ip:192.168.1.17` received two maps (102,400 bytes)
in 0.187 seconds and eight fine packets (1,024 bytes) in 0.211 seconds with the
same continuity and zero-fault result. The initial connection immediately after
RAM boot timed out before the network was ready; a bounded retry after network
readiness passed.

The map device is one continuous acquisition session per FPGA reset epoch.
Stopping and reopening it can expose a delayed source-rate discontinuity and
latch hardware-health fault `0x40`; `acquisition_flush` cannot erase hardware
history. PPU now flushes before the first start, rejects a second session in the
same client, and rejects an epoch whose driver has already delivered a map.
Consumers keep one map buffer open across dwell/role boundaries. Fine streams
remain restartable.

## Fine-correlation defect and correction

The first native cabled run produced a strong coarse response but only about
`0.048` median normalized fine correlation. Its packet envelopes, coefficient
energy, scheduling, and period fit were valid, which localized the discrepancy
to coefficient values rather than transport.

The generator/C-tool memory format encodes I in bits `31:16` and Q in `15:0`.
The FPGA coefficient register accepts I in `15:0` and Q in `31:16`. The initial
PPU file loader preserved the file word and therefore interchanged I/Q at the
FPGA. Energy is invariant under that swap, explaining why structural checks
could not detect it.

PPU main commit `7fa26455417f52cadd4d1968147dbd47d1e64383` corrects the
conversion and adds:

- byte-exact coefficient-layout regression coverage;
- expected-serial binding for USB and Ethernet PSS contexts;
- the qualified C-equivalent three-map drift/robust analyzer;
- explicit canonical and source-rate candidate/period fields;
- fail-closed one-session coarse-map behavior; and
- correct propagation of operation `OSError` values through the shared radio
  lock.

PPU passed Ruff, strict mypy for all 74 source files, and 1,449 tests with 11
explicit hardware/browser skips. The commit is pushed to `origin/main`.

## Corrected cabled timing proof

The guarded runner introduced at firmware DNM commit `5fa73e9b1` used one
continuous map session: three muted maps, three transition maps after TX start,
and three positive maps. It then ran positive A, a phase-continuous
minimum-gain control, and positive B using restartable fine streams. Follow-up
commit `637e50a0d` reasserts and verifies the hardware ZERO source only after
cyclic-buffer destruction. A separate post-context enforcement and reopen is
still required to cover the later IIO-context teardown, as the 30 MS/s work
below demonstrates.

The positive coarse maps measured peak-to-median `3.7084` and robust-z `59.51`,
compared with muted `1.3411` and `4.79`.

| Role | Results | Fitted period (source samples) | Worst residual | Median normalized score | Winner lag |
| --- | ---: | ---: | ---: | ---: | ---: |
| Positive A | 128 | 80,000.087733 | 0.5157 sample / 8.59 ns | 0.43432 | 13..25 |
| Minimum-gain control | 64 | not qualified | 129.2827 samples | 0.02079 | -118..120 |
| Positive B | 128 | 80,000.088030 | 0.4988 sample / 8.31 ns | 0.43445 | 13..24 |

Both positive scores exceeded the muted-control median by more than 20 times.
Both fitted periods were within one source sample of 80,000; both positive
worst-case residuals were within one source sample; neither positive run hit
the search-aperture edge. All map/tracker/push/validation fault gates passed.

Cleanup restored `.17` to 30.72 MS/s and 18 MHz bandwidth. The cabled-run
receipt proved `.18` safe through minimum gain, TX LO power-down, zero DDS
amplitudes, and buffer release. Its selector readback preceded buffer release,
however, so a separate post-fix close-and-reopen inspection was performed.
That independent inspection proved stable selectors `[3, 3]` (hardware ZERO),
gain `-89.75 dB`, TX LO power-down, and four zero DDS raw values after buffer
release. Final PPU recovery proved USB departure/return, route release,
persistent AD9361 1R1T identity, firmware
`v0.48-plutoplus-spf-iq-direct-async-v3`, and unchanged QSPI SHA-256
`07e6163bb27837eef080a885d8b116b7524f3693f2455c86b1d56724eaa77eb7`.

This proves synthetic cabled 60 MS/s PSS timing and result transport. It does
not claim 60 MHz analog bandwidth, live Starlink reception, SSS, or frame lock.

## Evidence identities

- v5 DFU:
  `7c5f5c3b8307cc49fadbe416da5f19ceb86350c0ddd9e6bd15f98cd423dd1038`
- USB maps:
  `361e72dce0dff393019dad41235bd1a0bc506ab6003a56ac257f5bb2d1f6874e`
- USB fine packets:
  `baa38f3562b3e1910f3ad41ecd65d22926b89ad7263e0cd5ad12eb87479e5e10`
- Ethernet maps plus fine packets:
  `da8e55c166d835e2020a871c5b898c5fdffc5373b549fad697a2a43f0bb03cd8`
- corrected cabled run:
  `4b9243e62b5349b99cb9d36637e13a9d6528cef8a67f0cd63f595d62d3f4795c`
- final RAM deployment:
  `0d0b63019574808e293612d8621ff4d895b96d7243da4cfdc9575987893618ef`
- final recovery:
  `ea43484679438c71e4d3313195ac0f4fe3344f7585d57396b6cb476342fa1ee6`
- independent post-release TX mute verification:
  `e2f553307a92b4362c645d3dbe670a04ba3bf259013e2748c9e04e7269ff3b6e`
- guarded runner source:
  `322b754f48fb8b10ad7faaffb78834bb4ce4ee14aa8e77ed069bfcd6eafdd65f`

Evidence root:

`/home/mouse9911/pluto-state/starlink-rx-only-dnm/iio-v5-20260907`

## 30 MS/s routed and cabled qualification

M6 used the same detector-only acquisition/tracker architecture at a 30 MS/s
source rate. The rate-specific tracker contains 132 Q15 taps and searches 121
full-rate lags (`-60..+60`). The acquisition engine retains its factor-two DDC,
so its canonical map rate is 15 MS/s and the host converts map candidates back
to 30 MS/s source indexes before scheduling fine requests.

The fresh Vivado 2022.2 routed build passed with setup WNS `+0.341 ns`, hold WHS
`+0.015 ns`, no routing errors, 12,047 LUTs, 19,562 registers, 4,392 of 4,400
slices, 49.5 BRAMs, and 55 DSPs. The routed structural validator found the
expected tracker and acquisition structures, no RX or TX DMA hierarchy, no
tracker critical CDC paths, and exact rate parameters of 30 MS/s.

The rate-identified `starlink-pss30-iio-v1-dnm` image was RAM-booted only on
`.17`. Its deployment attested the detector-only device tree, AD9361 1R1T
identity, frame-metadata-v3, and the expected empty TX/RX-DMA layout. The
canonical cabled repeat used one continuous coarse-map session followed by
positive A, a phase-continuous minimum-gain control, and positive B.

| Role | Results | Fitted period (source samples) | Worst residual | Median normalized score | Winner lag |
| --- | ---: | ---: | ---: | ---: | ---: |
| Positive A | 128 | 40,000.045928 | 0.5059 sample / 16.86 ns | 0.72139 | 7..13 |
| Minimum-gain control | 64 | not qualified | 60.4827 samples | 0.04197 | -59..51 |
| Positive B | 128 | 40,000.044331 | 0.5091 sample / 16.97 ns | 0.73175 | 7..12 |

The positive coarse peak-to-median was `12.3837` with robust-z `167.35`, versus
muted `1.3395` and `4.67`. Both positive fine scores exceeded the control by
more than 17 times. Both fitted periods and worst residuals were within one
30 MS/s source sample (`33.33 ns`), neither positive role touched the
search-aperture edge, and all map, tracker, validation, and push fault gates
were zero.

An independent reopen after the first numerical pass caught that destruction
of the TX streaming context could still restore DAC selectors to `[0, 0]`.
Gain remained at `-89.75 dB`, the TX LO remained powered down, and all DDS
values remained zero, but the strict hardware-ZERO invariant was not satisfied.
The guarded runner now creates a separate post-teardown context to enforce ZERO,
destroys it, opens a second fresh context, and makes exact serial, selectors
`[3, 3]`, four zero DDS raw/scale values, minimum gain, and TX LO power-down a
mandatory pass gate. The same fail-safe barrier is attempted on every error
path. Eleven focused runner tests pass, including rejection of each unsafe
field and the two-fresh-context lifecycle.

The complete firmware-branch test suite reported 1,922 passed, five skipped,
and five failed. The five failed assertions consume branch-head files untouched
by this work: the wide-metadata synthesis-option contract, two historical
manifest hashes for `tools/starlink_pssctl/Makefile`, the sealed ABI-12
minimum-host-lead contract, and the integrated-release CDC-argument count. The
three files changed for this qualification do not overlap any failed test input;
the focused runner suite remains 11 of 11 passing. Historical manifests were
not rewritten to conceal that drift.

The corrected hardware repeat passed that new gate. A further read-only reopen
after the complete run again observed selectors `[3, 3]`, four zero DDS raw and
scale values, gain `-89.75 dB`, and TX LO power-down. Cleanup restored `.17` to
30.72 MS/s and 18 MHz bandwidth. Recovery proved USB departure/return, route
release, persistent firmware `v0.48-plutoplus-spf-iq-direct-async-v3`, AD9361
1R1T identity, and unchanged QSPI SHA-256
`07e6163bb27837eef080a885d8b116b7524f3693f2455c86b1d56724eaa77eb7`.

This proves synthetic cabled 30 MS/s PSS timing and native result transport. It
does not claim live Starlink reception, SSS, or final frame lock.

### 30 MS/s evidence identities

- candidate artifact index:
  `435bae84f53902793ba02f2120785c0966bc411b56fd3aa25eeae2c1291e2199`
- candidate plan:
  `a9eec9dc68eb3e7ed15a14dd9a2b3e64d9322d2d1f9ec0a7f5ab44516bb0a4ac`
- routed-validator log:
  `7cbd479b2685e42cea15d47a66e90fd84e1e0b9919e5c8e68b09bfc37beb768c`
- DFU image:
  `ec00dfcbcc999f6011c980c98ffc5ee21f61172296b7865df795a7c28dd28931`
- corrected-repeat USB inventory:
  `8adb5d1997e9a594935536f739d8e1de583d3493e7ade69f24ddd7270106fc63`
- corrected-repeat operation plan:
  `11708551c78ed8db6b31a0fe573380a91ff09aaa5920c6f194961814311094f3`
- corrected-repeat RAM deployment:
  `4aaa0290a96c8458eaf6a9a93559b6ef3667325a40a045ec5627e5a4f312706f`
- corrected-repeat cabled run:
  `7ec27f5a3cab308667ee6217eb49a8839cdd64e46e7fc26691fea3097434d60f`
- corrected-repeat recovery:
  `3afe13be1c99c2e79d1d4df0a881e09ba6f85b11b787335a6f5a24550acecd61`
- corrected guarded runner source:
  `1e21370e1f2a185bc9115c046d212c75007cb0cc96a1b70752781ed908bd1904`
- focused runner test source:
  `4059c3e024c944c8380f9541ba3547a696bd2bd0f2df8c530914f01793203169`

Evidence root:

`/home/mouse9911/pluto-state/starlink-rx-only-dnm/m6-30-native-iio-20260907`

## 30 MS/s Ethernet result-transport qualification

The guarded cabled runner accepts an explicit `usb` or `ethernet` receiver
transport. Ethernet is fixed to `ip:192.168.1.17`; the PSS client still rejects
the context unless its IIO serial is exactly `.17`. The transmitter remains
bound to `.18` at USB topology `3-11`.

After RAM boot, the first three-packet ping preceded LAN readiness. A bounded
readiness retry then proved both ICMP and TCP port 30431 before the sole coarse
map stream was opened. Tomorrow's live runner must retain this readiness gate:
an early connection failure must never consume or restart the one-session map
epoch.

The complete positive/control/positive cabled qualification then passed with
all `.17` map and fine-result data transported over Ethernet:

| Role | Results | Fitted period (source samples) | Worst residual | Median normalized score | Winner lag |
| --- | ---: | ---: | ---: | ---: | ---: |
| Positive A | 128 | 40,000.044509 | 0.5435 sample / 18.12 ns | 0.73201 | 7..12 |
| Minimum-gain control | 64 | not qualified | 67.5466 samples | 0.04061 | -59..59 |
| Positive B | 128 | 40,000.045653 | 0.4942 sample / 16.47 ns | 0.72767 | 7..13 |

The positive coarse peak-to-median was `12.1245` with robust-z `169.61`, versus
muted `1.3947` and `5.24`. Both positive periods and residuals stayed within one
30 MS/s source sample, no positive result touched an aperture edge, and every
map, tracker, push, and validation fault gate remained zero. The mandatory
post-context TX enforcement and independent reopen passed, and a further
read-only `.18` reopen after the run again proved selectors `[3, 3]`, four zero
DDS raw/scale values, `-89.75 dB` gain, and TX LO power-down.

Recovery returned `.17` to persistent
`v0.48-plutoplus-spf-iq-direct-async-v3`, AD9361 1R1T, and proved unchanged
QSPI. The deployment receipt also passed offline replay verification.

### 30 MS/s Ethernet evidence identities

- USB inventory:
  `ef05f3aa4ff7ddf4785ec22200bcccac79b9d98270d0901977face6979641906`
- operation plan:
  `738bc0e140c0860a80309ee96fe21a68d15cd06c757a0dde38974d217a66b9ce`
- RAM deployment:
  `7729587289991dd0646de5540830f5cc6a17c7b1feb64b9a1e88005b89a54ec1`
- Ethernet cabled run:
  `b676f2d220a859e792f1b9d19ce91371e18c0db08b4c603c11e0e724de07bcd6`
- recovery:
  `1e98fd7f5c497e9964e577a7d973da1845af70c2cb1f85d1032fc160264b035f`
- Ethernet-capable guarded runner source:
  `163571264beef0d9aefc9badc6e22e2cf7f174b78e97110e2f61f60081936750`
- focused runner test source:
  `031d9d2049141124884666f81534ecf221b7faa865de53368c0860d3efe88cca`

## 30 MS/s RX-only Ethernet soak

The native map-soak runner exercises the live result path without opening a
transmitter. It binds the IIO context to `.17` by exact serial, holds the radio
lock through stream shutdown, RF restoration, and IIO context destruction, and
uses one uninterrupted map session for the complete dwell. It hashes every
logical map while retaining only compact first/last summaries, so evidence size
does not grow with the raw map payload. Seventeen focused tests pass, including
a lifecycle test proving that the lock is released only after cleanup.

The 120-second Ethernet run passed at 30 MS/s:

| Measurement | Result |
| --- | ---: |
| Elapsed time | 120.072824 s |
| Complete maps | 1,407 (minimum 1,404) |
| Driver chunks | 281,400, exact |
| Logical map bytes | 56,280,000 |
| Ethernet transport bytes | 72,038,400 |
| Mean transport rate | 599,955.91 B/s / 4.80 Mbit/s |
| Map generations | 1..1,407, continuous |
| Canonical start increment | 1,280,000 samples, exact |
| Source start increment | 2,560,000 samples, exact |
| Fault and push-failure gates | all zero |

The complete logical-map digest is
`cf8dfcaa921754d13651b9dd32cb3fdad5a4c9b5cc5827ef26301a45860bc651`.
The final three noise-only maps produced peak-to-median `1.3602` and robust-z
`4.853`; this is transport-health evidence, not a PSS detection claim.

Cleanup restored `.17` to 30.72 MS/s and 18 MHz bandwidth. Recovery proved
USB departure/return, route release, persistent
`v0.48-plutoplus-spf-iq-direct-async-v3`, AD9361 1R1T, and unchanged QSPI
SHA-256
`07e6163bb27837eef080a885d8b116b7524f3693f2455c86b1d56724eaa77eb7`.
The candidate deployment receipt also passed offline replay verification. The
run made no persistent write and never opened `.18` or any other transmitter.

### 30 MS/s RX-only soak evidence identities

- USB inventory:
  `5494a3b471d74b68f5e48d5a56662880e14412a154bbbdc398849787222e995f`
- operation plan:
  `2d474a76a5ea50492f7fb10480949df9be905db11d089e1d976ccea57b29e331`
- RAM deployment:
  `a68119da35247f840802c71f7da9c12b4e7d2c59ed63b976bb31003fe24775cc`
- 120-second Ethernet soak:
  `faa76b13a49ff069eb99cfedef89ced6543139067483ce154b20b0ebd7d5a079`
- recovery:
  `8b9c826c2ddeeef847a67a624c117827eb074410272434e6dd948cc6ee80c970`
- map-soak runner source:
  `a51ea64953a2b57c13c93e30a5af88d397ca1d1565e0efc37d043e34bf2fe253`
- focused soak test source:
  `e70ae88b73d47b686d7f7d97c4f63a7bd4f7fdb075ee049303e0025b5b6fc557`

Evidence root:

`/home/mouse9911/pluto-state/starlink-rx-only-dnm/m6-30-native-iio-20260907/hardware-attempt4`

## Live fixed-IF preparation

The RX-only soak runner accepts an explicit `--rx-lo-hz`. The value is checked
before an output directory or radio context is created and must lie in the
AD9361 tuning interval from 70 MHz through 6 GHz. The cabled qualification path
retains its 2.4 GHz default, so this does not change any earlier evidence.

For the frozen channel-4 upper-edge geometry and a 9.75 GHz low-side LNB, the
declared receiver IF is 1,937,500,000 Hz. After the matching 30 MS/s image has
been RAM-booted and Ethernet readiness has passed, the first noise/live
observation command is:

```text
scripts/starlink_pss_native_iio_soak_v1.py \
  --rate-msps 30 \
  --receiver-transport ethernet \
  --duration-seconds 120 \
  --rx-lo-hz 1937500000 \
  OUTPUT_DIRECTORY
```

The receipt records both the requested LO and exact AD9361 readback, holds the
`.17` lock through RF restoration and context destruction, opens no
transmitter, and makes no PSS claim from a noise-only run. On-channel evidence
must still be compared with the declared off-slice control and repeated
on-channel role before promotion to M4/M9.

Commit `7c89a4781` was then exercised on `.17` with a fresh RAM-only 30 MS/s
boot and the requested 1,937,500,000 Hz IF. The AD9361 readback matched exactly.
The 1.034-second Ethernet smoke delivered 12 continuous maps and 2,400 exact
chunks with every map, tracker, validation, and push-failure counter at zero.
It restored the prior 30.72 MS/s, 18 MHz, 2.4 GHz settings before closing the
context. The final noise-only estimate was peak-to-median `1.3674` and robust-z
`5.3048`, correctly below the frozen live-candidate thresholds and therefore
not a PSS claim.

The deployment receipt passed offline replay verification. PPU recovery then
proved USB departure/return, route release, persistent AD9361 1R1T firmware,
and unchanged QSPI. `.18` and all other radios were not opened.

### Live-IF smoke evidence identities

- USB inventory:
  `3569e9c3271c9237081e03e641f85ecf900889a5e4070aa674dfcabbac7946a8`
- operation plan:
  `b0b4c5cdefc590ccea6aea1396438014f485713e9c788c2f5a4e78cea9590a92`
- RAM deployment:
  `c42b49ec8ce0de466b382c59f12fa6381a3612dcf3fa4f51ec3348b1e787bb74`
- explicit-IF Ethernet smoke:
  `42bf524c24417a7f14760dbd00065ed01579fb72038c2ca159259a360a9cbc02`
- recovery:
  `586f3cc4b9397ad0d33a3c43195c2fcc473876f316967dcd1abdfd84f2957af8`
- LO-capable cabled/receiver helper source:
  `9c45e3f92b86f24e33a65bae2caa4a005e1a88bac157af3d98bc071bccbe7aa9`
- LO-capable soak runner source:
  `488d6efe7de569c35596b16e46e1933083bada8e441556650e09cb57c4cad209`
- focused soak test source:
  `2bde1d155eb5689ee032636d51cd31b08fb539e4c9c5caf6b1dd8e35e34c8f50`

Evidence root:

`/home/mouse9911/pluto-state/starlink-rx-only-dnm/m6-30-native-iio-20260907/hardware-attempt5-live-if-smoke`

## Complete live timing trajectory and replay qualification

The native soak now analyzes every rolling three-map window while the one map
session remains open. Its receipt retains all timing estimates and requires the
estimate count to equal `complete_maps - 2`. The large trajectory remains in
the evidence file; the terminal output is a bounded summary. A local benchmark
processed 28.3 windows/s versus the fixed 11.72-map/s FPGA production rate.

The committed implementation then ran for 120.039 seconds at 30 MS/s and the
channel-4 upper-edge IF of 1,937,500,000 Hz. It received 1,406 contiguous maps,
281,200 exact transport chunks, and exactly 1,404 rolling timing estimates.
All map, tracker, validation, and push-failure counters remained zero while the
host performed the analysis in real time. The complete logical-map digest was
`6934e1a29b714b66e0a84d537d2ff3c782f79963a56c7f76182a981e6e94ee39`.

The separate replay-only qualifier validates every overlapping window's
generation, canonical start, source-rate scaling, drift hypothesis, period,
coefficient identity, map/chunk accounting, cleanup, and source-receipt hash.
It applies the frozen M3/M4 thresholds without opening a radio. It also accepts
three exact role analyses and permits a PSS-timing claim only for a passing
positive-A/off-slice-control/positive-B campaign with at least 30 MHz control
separation and `1.10x` positive-to-control median contrast. SSS and frame-lock
claims remain hard false.

Applied to this no-LNB run, the replay result is a passing negative control:
10 of 1,404 instantaneous windows passed (`0.7123%`), the longest consistent
track was one window, median peak-to-median was `1.34474`, and median robust-z
was `4.84568`. The positive-track policy rejected it. This is the measured
false-alarm baseline for the corresponding live observation, not Starlink
evidence.

After the run, PPU recovery proved USB departure/return, route release,
persistent AD9361 1R1T firmware, and unchanged QSPI. `.18` and all other radios
were not opened. Twenty-six focused acquisition, replay, campaign, and cabled
tests pass.

### Complete trajectory evidence identities

- USB inventory:
  `ccf5245debb4e75bd3c31c5b39a3f467de306b91518e77a72acb3290fc4435c2`
- operation plan:
  `b3196df2e28f9a10f8fc086130649bf1234a05db81208118727b6d3e83690068`
- RAM deployment:
  `fed4bc3d0bd3bc38429c17b7c368b9b4a38df22850dd5656b7bac85908ce4362`
- 120-second trajectory receipt:
  `1e9305dc39143774537887b8e7a063f74dbe7403182b94b3aafb47de5a8f5440`
- replayed noise-control analysis:
  `b9ad7339cccc98a2adec1b00cd7752417f679ee5759669482be7d777647b6d83`
- recovery:
  `010d87483b5b0ed49588d24decc938d4cef55c1720921e38ec913240dbd3f57d`
- trajectory-capable soak source:
  `e98742018bf4023ad37432095aebd7e916480fd19e12fbcb9a7707d463866615`
- soak test source:
  `b4fdbccf6c1a4a8dd0965f9e321b8aa445518e4b7e2a98b436ee9a4ed3f6128d`
- replay/campaign qualifier source:
  `3c0677ea2cba0b2a788fac4259ab7e9fbaeaa28371d17a8b9c69161ef6db126e`
- replay/campaign test source:
  `22d50e8dd5f68fe3e36aa7bdef758ba5906bea016976f857aa45099e3b51222b`

Evidence root:

`/home/mouse9911/pluto-state/starlink-rx-only-dnm/m6-30-native-iio-20260907/hardware-attempt6-live-trajectory`

## Single-epoch native live campaign

The native live runner closes the Ethernet-only operational gap: `.17` can be
RAM-booted while locally attached, moved outside without losing power, and then
complete positive-A/off-slice-control/positive-B without another USB or FPGA
reset. It opens the FPGA map buffer exactly once and retunes only the AD9361 RX
LO between roles. Each retune waits 200 ms and drains five complete maps before
the next role starts, preventing RF-settling and rolling-map contamination from
entering the decision.

Each role retains its complete rolling timing trajectory. Global accounting
includes all role maps plus both five-map transition guards, and requires exact
driver map/chunk counts, continuous generations and canonical/source indexes,
the active coefficient generation, and zero map/tracker/validation/push faults.
Signal classification does not control acquisition success. A PSS timing claim
requires all three roles to last at least 120 seconds, both on-channel roles to
pass the frozen positive-track policy, the off-slice role to pass the negative
control policy, at least 30 MHz frequency separation, and at least `1.10x`
median contrast. SSS and frame lock remain hard false.

The separate replay verifier checks an exact field and gate inventory,
coefficient identity, every role window, all ten transition maps, cross-retune
continuity, receiver settings, cleanup, and synchronization claims. Unit tests
prove one buffer open, cleanup before lock release, and rejection of forged PSS
or omitted epoch gates.

The committed path passed a short structural hardware campaign on `.17` at
30 MS/s. One uninterrupted epoch followed
`1,937,500,000 -> 1,887,500,000 -> 1,937,500,000 Hz`, delivering 46 contiguous
maps and 9,200 exact chunks. The three one-second roles each retained 12 maps
and 10 timing windows; both transition guards discarded exactly five maps.
Every fault gate was zero and RF settings were restored. Independent replay
passed but correctly kept `pss_detected=false` because the 120-second duration
gate was false. This is structural/no-LNB evidence only.

The production 30 MS/s command, after RAM boot and Ethernet readiness, is:

```text
scripts/starlink_pss_native_iio_live_campaign_v1.py \
  --rate-msps 30 \
  --on-lo-hz 1937500000 \
  --off-lo-hz 1887500000 \
  --role-duration-seconds 120 \
  OUTPUT_DIRECTORY
```

The same runner accepts `--rate-msps 60` after the 60 MS/s detector image is
RAM-booted. The frequency geometry and decision policy remain identical; map
indexes are converted by the rate-aware native client.

After the structural run, PPU recovery proved USB departure/return, route
release, persistent AD9361 1R1T firmware, and unchanged QSPI. `.18` and all
other radios were not opened. Thirty focused native acquisition, single-epoch,
replay, campaign, and cabled tests pass.

### Single-epoch campaign evidence identities

- USB inventory:
  `8a5e0723704241631a5682c1fff4c6c5df574205da6c84fa8d4a2c60a7d38b1c`
- operation plan:
  `33d419845086fdd55d31e460bdfec2f8def298722c0d5bfecbd00d80ad49d08f`
- RAM deployment:
  `eba0507f7f8f0cf09b59ceb7a0bbda1e2538e244bf3de3889b652c3d91dd628b`
- structural campaign:
  `11dd0e3de207893b283ba0f30b9be0277ab71090929c17b730b34c9b211c88bf`
- independent campaign replay:
  `e7273afa0117d6eddf7311da6c1f8cc879a7904d99c4ead3c6d60917add0dad6`
- recovery:
  `cf2f506c104695a835a10ac7c1382cff81a292402d6396749fcb840036f5d865`
- single-epoch runner source:
  `2d3edba6be0fded8ed3702ed37cf8cb715dbfbf41380d5f88692e8203c3a96ca`
- replay/qualification source:
  `f2684d1ffe0ba5069686b0593414ac86b4c73875cd029d522dae242a45fa85cd`
- single-epoch test source:
  `5174e440c791b417dec7c49f23dddfacb843543336ff9368e53aa44915abd168`
- replay/qualification test source:
  `c77af85f3df861644f0db9e6c96807bc2bd719ea35b4392d6c08c2970dd7c6e8`

Evidence root:

`/home/mouse9911/pluto-state/starlink-rx-only-dnm/m6-30-native-iio-20260907/hardware-attempt7-single-epoch`

## 60 MS/s single-epoch structural qualification

The same committed runner and replay verifier passed the corresponding short
structural campaign at 60 MS/s on `.17`. The sealed
`starlink-pss-iio-v5-dnm` detector-only image was loaded into volatile RAM with
the exact PPU commit bound by its candidate plan. The RAM lifecycle attested
serial `104000bac4950008230026001b440a003a`, AD9361 1R1T, detector-only FPGA
topology, TX quiesce, and unchanged persistent QSPI before the campaign began.

One uninterrupted map epoch followed
`1,937,500,000 -> 1,887,500,000 -> 1,937,500,000 Hz`. It delivered 46
contiguous maps and exactly 9,200 transport chunks. Each one-second role
retained 12 maps and 10 overlapping timing windows, while each retune guard
discarded exactly five complete maps. The active coefficient, driver counts,
role counts, epoch continuity, and every tracker/map fault and push-failure
gate passed. Cleanup restored the receiver's prior 30.72 MS/s, 18 MHz, 2.4 GHz
configuration before releasing the radio lock.

Independent offline replay passed the exact receipt and 60 MS/s source-index
conversion. It correctly retained `pss_detected=false`, `sss_detected=false`,
and `frame_lock_claim=false`: the one-second roles do not satisfy the required
120-second live duration, and this no-LNB structural run is not signal
evidence. Recovery then proved USB departure/return, route release, the
persistent AD9361 1R1T firmware, and the same QSPI SHA-256
`07e6163bb27837eef080a885d8b116b7524f3693f2455c86b1d56724eaa77eb7`.
`.18` and all other radios were not opened.

The production 60 MS/s command, after RAM boot and Ethernet readiness, is:

```text
scripts/starlink_pss_native_iio_live_campaign_v1.py \
  --rate-msps 60 \
  --on-lo-hz 1937500000 \
  --off-lo-hz 1887500000 \
  --role-duration-seconds 120 \
  OUTPUT_DIRECTORY
```

### 60 MS/s structural evidence identities

- sealed candidate plan:
  `646874991bfaac921b8cadc7ac7012773b9d37ee57eeac0c96a5143cb37001e0`
- sealed RAM DFU:
  `7c5f5c3b8307cc49fadbe416da5f19ceb86350c0ddd9e6bd15f98cd423dd1038`
- USB inventory:
  `cf8b5d75dc39e670e91f85ea530b5e759d7e83e3d820b2400dcf9c3455be795c`
- operation plan:
  `4429734417d4c24e01175cee91ab81e744b5b9b6ba68a85239bfc87453ca3e07`
- RAM deployment:
  `61bdd721b1d9d8db464e1f79409ff0bc8b0190747e5b3bc48c1b081e58ee0f6e`
- structural campaign:
  `77e51df046621fcbdcd55f53cc3dc3a48bd319d9f4cadd9fed181fc6697abcd1`
- independent campaign replay:
  `b19a2943474312136c85612499813efa7948bde59ba4c99005505f0a3e5a2f03`
- recovery:
  `3e3be85de78dc8b503735edf1d7262b99a8ef582d78f7fe45d5c37579c2d245d`
- single-epoch runner source:
  `2d3edba6be0fded8ed3702ed37cf8cb715dbfbf41380d5f88692e8203c3a96ca`
- replay/qualification source:
  `f2684d1ffe0ba5069686b0593414ac86b4c73875cd029d522dae242a45fa85cd`
- single-epoch test source:
  `5174e440c791b417dec7c49f23dddfacb843543336ff9368e53aa44915abd168`
- replay/qualification test source:
  `c77af85f3df861644f0db9e6c96807bc2bd719ea35b4392d6c08c2970dd7c6e8`

Evidence root:

`/home/mouse9911/pluto-state/starlink-rx-only-dnm/iio-v5-20260907/hardware-attempt8-single-epoch`

## Persistent 30 MS/s live coarse acquisition

PPU `main` gained reusable, exact-image lifecycle support for the detector-only
30 MS/s image. A local `.18` canary completed 30 MS/s persistent deployment, a
five-second native-IIO functional soak, and exact rollback to its prior v7
firmware. PPU then promoted the LAN profile, learned to attest an RX-only source
that intentionally has no DDS, and added detector-only guarded network reboots.
The complete PPU suite passed after each change; the final bound PPU commit is
`07591644a1523515e1094ac05c197b718b5dede8` on pushed `main`.

The promoted network operation wrote only the authorized `.17`, returned exact
serial and AD9361 1R1T identity, and attested firmware
`starlink-pss30-iio-v1-dnm`, FIT SHA-256
`ca1ba8b794f9a91d8bf4674aa7121498a92758bf00453884d33b8b427fa26e95`,
full QSPI SHA-256
`031c065580492a026f838fcd7fafe4f70a2744c61e34ec77e03201f676accd02`,
and the intended absence of DDS, TX DMA, and RX DMA. Every subsequent map-counter
reset used the guarded non-persistent PPU reboot and continued both the prior
boot ID and prior SSH-known-host hash.

The first corrected fixed-LO campaign transferred 4,238 maps, 847,600 chunks,
and 216,985,600 bytes without a fault, restored RX exactly, and replayed
independently. It remained unqualified: short on-channel excursions did not
meet the frozen 80 percent trajectory-occupancy policy. That result showed the
need for the same interleaved LO scan that had qualified the intermittent live
signal at 15 MS/s.

Schema v3 therefore scans 25 offsets in the sealed order
`0,+100k,-100k,...,+1.2M,-1.2M` for on-channel A, the below-band control, and
on-channel B. Each point waits 200 ms, discards ten complete maps, and retains
34 maps for exactly 32 rolling trajectory windows. One map epoch covers all 75
points. Even at the positive edge of its scan, the control's complete 20 MHz
passband ends 88.8 MHz below the declared 10.700 GHz Starlink boundary. The
runner binds the exact persistent-deployment receipt, every ordered reboot,
current known-host identity, coefficient, firmware and PPU source commits,
continuous generations/indexes, all driver counters, and exact cleanup. Its
full mocked 3,300-map epoch, independent replay, and tamper rejection pass.

The first two v3 epochs were retained as clean unqualified observations. The
first had no positive point in either on-channel role. The second showed an
intermittent event—A reached 17/32 passing windows at +600 kHz and B reached
16/32 at -200 kHz—but correctly remained below the frozen 26/32 and eight-
consecutive-window gates. No threshold or scan parameter was changed afterward.

The third v3 epoch qualified. A passed at -100 and -200 kHz and B passed at
-100 and -200 kHz. Each role's best trajectory was 32/32 with a 32-window
continuous timing track. The best A/B median peak-to-background ratios were
`1.805738` and `1.676775`, median robust z scores were `10.9403` and `8.9822`,
and worst local timing residuals were seven and six canonical samples. At 15
MS/s canonical resolution those bounds are approximately 467 ns and 400 ns;
they are coarse seeds, not the final 30 MS/s timing bound. The below-band
control had zero passing points, and the conservative positive-to-control
median contrast was `1.240001`, above the frozen `1.10` gate.

All 3,300 maps, 660,000 chunks, 132,000,000 logical bytes, and 168,960,000
transport bytes were exact. Every map, tracker, validation, and push-failure
counter was zero. Cleanup restored 30.72 MS/s, 18 MHz bandwidth, 2.4 GHz LO,
slow-attack AGC, and LO power state exactly. Independent offline replay passed
and reproduced the PSS claim without hardware access. SSS and frame lock
remain hard false.

Evidence identities:

- deployment receipt:
  `104474f2b1905be02039535814720c08828752d58cbc5204e4e817159efbe2f1`;
- final guarded reboot receipt:
  `f62bfc6f5546551e01b80ce228dde412ae19fa15e3da7522fb9048c427fcc58b`;
- fixed-LO receipt and replay:
  `ff706ce52e712b2ee4e99677fd4f210f4cc647ab3da4255d8151de31c27e026e`,
  `e7099c323951b6988b9621a68c46ed7ff1a222cc4b21f2fcfe2740b33aa6a241`;
- v3 unqualified receipts:
  `d5c980ee11559ac473c5c552d7ebe9b16c495d8ca5f4170735b647d4c19b2e65`,
  `997b59188bd8b93c32309583561d8628a537ba1eaa6919c5cac78a61a7a6aa76`;
- qualifying receipt and independent replay:
  `f9fbd5aaf99cdb66b7df2fc63868307d106759aecd9929fd1e873a4761107294`,
  `a2470ef11e0f62f7d0ed1b629772790956c02cea8f77e7fa71afbe129bbc482f`;
- v3 runner and focused-test source:
  `f9990fdb29a46a6b1c4493fe5a0c84a93757610566f6efd19d4a65431132747a`,
  `003196c03416fd7f359fe97cea2a03366ee88d1e8b14a88254ca6cf88680aa73`;
- frozen firmware source commit:
  `b2bd98fe58fc9b82d8bdf05a3026bd6e3f9ee493`; and
- authoritative root:
  `/home/mouse9911/pluto-state/starlink-rx-only-dnm/persistent-30-native-iio-17-20260908`.

This completes live 30 MS/s coarse acquisition only. It does not prove fine
template selectivity, SSS identity, or frame lock.

## Next gates

The original native live-runner design used a nearby `off_slice_control` for
the middle role. That is not a valid Starlink-negative control: both LOs remain
inside the same approximately 240 MHz downlink allocation, so changing the LO
can select a different occupied slice rather than remove the signal class.
Historical receipts remain immutable, but no future live claim may use that
control.

1. Preserve the qualified persistent 30 MS/s deployment and its PPU rollback
   path. Promote exact 60 MS/s native-IIO bytes only through the same separately
   reviewed local canary, exact-image RX-only topology, persistent return, LAN
   deployment, and rollback gates.
2. Reuse the qualified v3 on-channel / below-band control / repeated on-channel
   scan at 60 MS/s. Retain one continuous map epoch, ten post-retune discard
   maps, exact stream/counter accounting, and the complete ordered PPU reboot
   chain in independently replayable evidence.
3. Treat both 30 and future 60 MS/s campaigns only as coarse PSS acquisition
   and timing-seed evidence. The coarse map detector has fixed coefficients, so
   loading a tracker coefficient file cannot make the coarse map itself a
   mismatched-template control.
4. For fine timing, schedule full-rate tracker requests from the live coarse
   seeds at the same RF. Compare the matched PSS coefficient bank with an
   energy-matched, deliberately mismatched bank, and qualify normalized score,
   sub-sample timing continuity, aperture margin, queue accounting, and fault
   counters. Raw 30/60 MS/s IQ remains inside the FPGA.
5. Add cadence/CFO tracking only after matched fine timing is repeatable at 30
   and then 60 MS/s. Add SSS hypotheses and joint PSS/SSS consistency as a new
   gate after that, followed by explicit frame-lock acquisition/loss
   hysteresis. No earlier result is promoted retroactively to frame lock.
