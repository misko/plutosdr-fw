# Counter UTC v1 RC1: build and two-radio deployment ledger

Status: full image build running; no candidate deployed yet.

The user authorized development, testing and deployment on both locally
connected radios. The separate production scanner on 192.168.1.17 is outside
this deployment and remains running.

## Source and artifact identity

- Intended firmware version: `v0.52-plutoplus-spf-counter-utc-v1-rc1`.
- Trusted build source: `2640f9d532736560c78315f0bbe6d6f40d82536e`.
- Build: https://github.com/misko/plutosdr-fw/actions/runs/35528969627
- Firmware implementation lock: `counter-utc-v1-rc1-source/firmware-v1` at
  `f0650dc0bdbae49150787658e9b82f8a8658d2ba`. The build commit adds only the
  manifest's reference to this immutable implementation lock.
- iiOD: `7aa544742e2718ff2f553dc35cb873510e02fbc4`, immutable tag
  `counter-utc-v1-rc1-source/libiio-v1`.
- Buildroot: `7f0a05e457e1e640c1ce403169844d3e5fbed623`, immutable tag
  `counter-utc-v1-rc1-source/buildroot-v1`.
- Host capture tooling: `pluto-plus-utils` commit `2b13ff2`.
- Approved ABI-3 host native runtime: `47a75cbc5e7d24a063b8b54eb531fdba6602b85c`,
  matching the working production host runtime. Counter-time queries use a
  separate raw TCP connection; the host runtime need not equal the iiOD source.
- The candidate retains the adaptive-scan RX0/TX2 topology in all FIT slots.

## Exact targets and recovery

| Radio serial | LAN address | USB topology | Original firmware |
|---|---|---|---|
| `1040007c4a94000211000b009186843ef2` | `192.168.1.18` | `3-11` | adaptive-scan v1 |
| `104000b29905000e17000800065934759d` | `192.168.1.15` | `3-8` | adaptive-scan v1 |

Identity was checked independently through interface-bound USB SSH and LAN
IIO. All four flash partitions of each radio were copied to private local
backup files and checked against on-device SHA-256 hashes. These private
backups and authentication files are excluded from release assets.

Both radios' persistent firmware payloads exactly match the public rollback
FIT. Downloaded rollback DFU/FRM/FIT hashes, sizes, DFU suffix and identical FIT
payloads were checked against the adaptive-scan-v1 release manifest:

- DFU: `f88c5fe44160f0a09031fb8b68f92b2280022e0f38174845b7edc3a37c26eea2`.
- FRM: `35bca4f5cfb6f9ec8a32692ceb2b55a20238a38bbff3e40fcd76789b765002a9`.
- FIT: `1f3ec2b6937e09a349e952a7bcc499a2902043f09f35c51fb0a5d50eb34d5403`.

## Completed pre-deployment checks

- Immutable remote source graph passes, including package pins and hashes.
- Release route preserves topology and requires the exact RC1 version.
- 31 host-runtime installer/preflight tests; receipt verified locally.
- Two explicit-radio/sample-rate CLI tests.
- Nine offline deployment refusal tests and four capture-continuity tests.
- Five-second baseline capture on each radio at 10 MS/s: 35 of 35 visits,
  zero skipped/invalid/cancelled visits, and receiver settings restored.
- Old firmware correctly reports counter-time queries unsupported; host
  capture succeeds and retains that truthful unqualified timing evidence.

## Remaining execution

1. Verify trusted build artifact hashes, packaged version, iiOD and FIT topology.
2. RAM-boot first radio, verify exact image/serial and run short smoke.
3. Run 300-second receive-only adaptive captures at 10/15/20 MS/s. Retain
   visit/counter/terminal/restoration evidence without full IQ payloads.
4. Require completed nonempty captures, no DMA-reported sample loss or IQ
   overlap, matching timing session/rate/boot identities, monotonic counters,
   and no timing collector errors. Assess <=50 ms query intervals separately.
5. Persist only with passing functional evidence bound to the exact image,
   serial and still-current RAM boot. Verify persistence after reboot.
6. Repeat on the second radio, then publish the tested candidate and public
   evidence. Preserve all failed attempts if any occur.

No independent UTC-timed RF reference has been identified. This campaign can
validate firmware behavior, counter progression and query latency, but cannot
establish physical +/-100 ms UTC accuracy. Calibration remains absent and the
capture evidence must remain UTC-unqualified. The release must disclose this
separately from firmware functional acceptance.
