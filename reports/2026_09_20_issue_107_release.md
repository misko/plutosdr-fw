# Counter UTC v1 RC1: two-radio release ledger

Both local radios are persistently running `v0.52-plutoplus-spf-counter-utc-v1-rc1`.
Functional hardware gates passed; physical UTC accuracy remains unqualified.
The production radio at 192.168.1.17 was not changed.

## Source and exact artifact

- Release: https://github.com/misko/plutosdr-fw/releases/tag/v0.52-plutoplus-spf-counter-utc-v1-rc1
- Trusted build: https://github.com/misko/plutosdr-fw/actions/runs/35528969627
- Actual image source: `2640f9d532736560c78315f0bbe6d6f40d82536e`.
- Implementation source lock: `f0650dc0bdbae49150787658e9b82f8a8658d2ba`.
- iiOD source: `7aa544742e2718ff2f553dc35cb873510e02fbc4`.
- Buildroot pin: `7f0a05e457e1e640c1ce403169844d3e5fbed623`.
- Companion PPU: `60486cf6f318959e1d8f7fd78c5b4289127c7867`.
- Companion tracker: `480f877ae237e2f8ed2880ca6d97a09cbe82bfa8`.
- Approved ABI-3 host runtime: `47a75cbc5e7d24a063b8b54eb531fdba6602b85c`.
- DFU SHA-256: `a2d29612a0d0a450b90a3f5a58af7ff8e9eeeecc0886404a40b27b5f8ebcaab1`.
- FIT SHA-256: `a31913380597375bacec3740984bbf59da285e686f4e9c4098e45ea4f8ada65b`.
- Packaged/running iiOD SHA-256: `66099bf0e6d968de302cbf412ccfdb3dc484690cd424d493593ca753e517b870`.

FPGA route passed: WNS 0.767 ns, WHS 0.019 ns. All FIT slots retain adaptive-scan
RX0/TX2 topology. Host and harness fixes do not change the built firmware bytes.
The original build provenance describes the state before radio testing; the final
release manifest and hardware summary record the subsequent canary acceptance.

## Accepted hardware captures

Every row represents 300 seconds of receive-only adaptive capture. Every planned
visit was delivered, with zero skipped, invalid, cancelled or DMA-reported missing
samples. Counter ranges did not overlap; expected retune gaps remain explicit.
Receiver settings and buffer counts were restored. Every query interval was
<=50 ms, inclusive anchor intervals <=10 s, and both capture endpoints were
covered within 10 s. The aggregates independently check the raw records.

| Radio (192.168.1.x) | MS/s | Delivered visits | Anchors | Max query ms | Max anchor interval s | Low-word wraps |
|---|---:|---:|---:|---:|---:|---:|
| 18 | 10 | 2138 | 63 | 9.708 | 5.017 | 0 |
| 18 | 15 | 2138 | 64 | 12.763 | 5.077 | 1 |
| 18 | 20 | 2137 | 65 | 31.296 | 5.069 | 2 |
| 15 | 10 | 2138 | 63 | 8.891 | 5.065 | 1 |
| 15 | 15 | 2138 | 64 | 10.585 | 5.073 | 1 |
| 15 | 20 | 2137 | 65 | 20.934 | 5.070 | 2 |

## Persistent deployment and recovery

- Radio 18: `1040007c4a94000211000b009186843ef2`, USB path `3-11`.
- Radio 15: `104000b29905000e17000800065934759d`, USB path `3-8`.

Each radio was independently identified over USB and LAN. All four original
flash partitions were backed up privately and verified. Original QSPI payloads
matched the public adaptive-scan-v1 rollback FIT
`1f3ec2b6937e09a349e952a7bcc499a2902043f09f35c51fb0a5d50eb34d5403`.

Each first RAM-booted the candidate. Persistent writes required this exact
image's successful RAM receipt, accepted three-rate evidence, matching live boot
UUID, serial and USB path. The supported SSH updater verified staged FRM, flash
layout, protected boot/environment regions and the written FIT before reboot.
Post-reboot checks verified a new boot UUID, exact persistent FIT and running
iiOD hashes, unchanged bootloader/NVMFS partitions, and a passing 10-second
10 MS/s capture with the new boot identity. These were software reboots, not
physical power-cycle tests. Raw environment comparisons show only the expected
`fit_size` update; all other stored key/value pairs are unchanged. Textual
`fw_printenv` parsing initially produced apparent script differences that direct
CRC-validated binary comparisons disproved. Public evidence excludes credentials
and backups.

## Failures retained and fixes

- Initial R18 RAM and R15 persistent LAN smoke attempts ran before networking was ready; no acquisition. Serial/firmware readiness was verified before successful retries.
- A smoke setup used an unrepresentable LO value; the harness now uses the exact
  readback value 1459687498 Hz. Settings restoration was retained.
- Initial R18 15/20 MS/s runs delivered IQ but failed the later independent
  <=10 s anchor-coverage gate. A busy SCANTIME response previously waited another
  five seconds; the host now retries a completed busy response after 50 ms.
  Both rates were rerun successfully; original reports remain in the evidence.
- Persistence preflights refused SSH banner-contaminated UUID parsing and an
  obsolete mass-storage execution path before any write. The harness now uses
  one strictly marked UUID and the existing controlled SSH flash gate.
- Real R18 five-second IQ smoke import was refused by the immutable complete
  300-second session contract. No downstream timing authority was created.
  Importer hardcoded R17 identity was fixed, with mismatch, malformed-evidence,
  R18 and R17-compatibility regression tests. Full real-IQ import is unvalidated.

## Software validation and remaining UTC gate

Prior checks covered six native C test executables, provider-enabled/disabled
builds, cross-language protocol decoding, ARM iiOD cross-build, 58 host tests and
109 tracker tests. Follow-up checks passed 33 counter-UTC tests, 73 diagnostic
tests, 16 deployment tests, seven capture-gate tests and nine importer tests;
these overlapping suites are not a combined distinct-test count. Focused lint,
formatting/type checks and host-runtime preflight passed. Release verification
checks the actual shipped DFU; manifest and payload hashes are published.

No independent UTC-timed RF reference has been identified. Kernel counter
snapshots attest coherence, not a maximum snapshot age. A low query RTT does not
prove acquisition-to-UTC alignment. Qualification therefore remains false and
TLE inference must not accept these records as independently bounded UTC.

Before claiming +/-100 ms, measure separate calibration and acceptance captures
against a UTC-timed RF marker with instrument/cable/detection uncertainty, bind
validated rate and acquisition-delay bounds to radio and boot UUID, replay the
full-span error bound, and validate real-IQ import/TLE sensitivity and runtime.
Reboot invalidates boot-bound calibration. RC1 is a prerelease, not this accuracy
qualification.
