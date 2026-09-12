# Pluto+ v0.50: physical 1R1T counter metadata

This release adds explicit counter-only metadata for physical AD9361 1R1T RX0. Applications can receive sample sequence numbers and exact dropped-sample counts without entering the paired tandem AGC path that previously returned `EOPNOTSUPP`.

Select manual gain, RX0, and source-rate decimation 1, then use PPU's `begin_metadata_capture(counter_only=True)`. Install its matching native runtime with `--metadata-abi 3 --counter-rx`. Counter metadata uses the versioned SPFC1 protocol; paired HOLD/AUTO remains a separate mode on 2R2T.

The kernel owns the counter stream's timestamp lifecycle and excludes competing owners and rate, LO, bandwidth, gain, gain-mode, and timestamp-control changes while capture is active. The release retains v0.49's FPGA source and exact DMA-queue admission.

## Verified results

Trusted Kalman run [34722030151](https://github.com/misko/plutosdr-fw/actions/runs/34722030151)
built firmware commit `619ecedf23a3fd2103e1237d69db830e26d8959c`.

- Physical 1R1T: 2.5/5/30/60 MS/s finite captures passed; 50 DMA buffers allocated exactly.
- Induced 60 MS/s loss: 229,000,000 missing samples matched counter intervals exactly.
- Paired 2R2T: RX0, RX1, and both receivers passed HOLD/AUTO in RAM and after QSPI boot.
- Invalid admission returned errno 95; protected configuration and competing ownership returned errno 16.
- Normal close, client SIGKILL, iiOD SIGKILL, and forced transport timeout released ownership and allowed recapture.
- QSPI reboot in both physical modes retained the exact FIT hash. Final public-API captures passed at 5/60 MS/s, with RX settings and queue restored.
- Final state: 1R1T, idle buffers, TX gain -80 dB, DDS disabled, TX LO powered down.
- Offline gates: 1,516 firmware tests plus RTL simulations; 3,454 PPU tests including exact release-profile gates; 14 native unit suites.

DFU SHA-256: `435a26369018e86ee66262b79c32895dbaaacef510a1efb71c566d6409555344`.
FIT SHA-256: `a53efc46f3c65d1a15e5063374551d2daa3cb9d0df51257de53b6af80be39493`.

## Qualification scope

The qualification report identifies the exact trusted-build DFU/FIT hashes and the only tested radio, serial `1040007c4a94000211000b009186843ef2`. See the attached manifest and report for measured results and deployment receipts.

Finite 60 MS/s capture is not a claim of continuous lossless 240 MB/s Ethernet streaming. At 60 MS/s, the qualification uses 50 MHz analog bandwidth. Counter-only metadata does not report paired gain, RSSI, detector validity, or RF accuracy. Qualification on one unit is not fleet qualification.

The existing FunctionFS supervisor can leave USB unbound after a deliberately killed iiOD; LAN capture and ownership recover, and a targeted gadget rebind restores USB. The actual timestamp packer/XPM simulation has known startup assertion warnings; it is a functional check, not an assertion-clean or exhaustive DMA proof.

Issue: https://github.com/misko/plutosdr-fw/issues/97

Matching PPU host release: [counter-rx-v1-host-v1](https://github.com/misko/pluto-plus-utils/releases/tag/counter-rx-v1-host-v1), source `d85199a5033e6cdf4ca735e24a440a9ea70d5329`.
