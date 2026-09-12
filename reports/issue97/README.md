# Issue 97: explicit physical 1R1T counter metadata

Implemented for the sole authorized radio `1040007c4a94000211000b009186843ef2`.
The candidate is `v0.49-plutoplus-spf-counter-rx-v1-rc1`, based on the verified
v0.49 release. Qualification and deployment results are recorded below and in
`qualification.json`; private maintenance backups remain outside version control.

**Deployment completed:** the candidate is persisted in QSPI and has rebooted successfully.
The stored FIT SHA-256 is `d1f5782d1a72c75383b6f8bfde340f144426723afe933cce6e7a20cad1f252b5`.
The public PPU API then captured 30 gap-free frames at both 5 and 60 MS/s,
with exactly 50 buffers and factor-one source/capture rate readback.
The radio is left idle in AD9361 1R1T; pre-capture settings were restored and TX remains muted.

## Implementation

A new explicit SPFC request selects an SPC1 counter frame on the existing ABI-3
transport. Physical AD9361 1R1T, RX0, manual gain, and decimation bypass are
required. Existing paired HOLD/AUTO bytes and behavior retain their contract.
The kernel owns a descriptor-scoped capture lease, excludes configuration
changes, and restores timestamp control when the owner closes or dies.
No paired gain/RSSI samplers or paired gain preparation run in counter mode.

The 80-byte little-endian frame carries full 64-bit sample intervals, exact
missing-sample counts, canonical CI16 geometry, stream identity, flags and CRC.
The FPGA prefix is two complex samples ahead of the first packed RX0 sample;
SPC1 explicitly identifies and applies that offset. Paired metadata keeps its
existing interpretation. A gap flag means a counter-observed missing interval,
not an independently measured ADC overload. Gain and RSSI observations are absent.

## Source and build

- Firmware baseline: `bc00edb8c340dd4f9b04361398cbd2c8edcc9cae`.
- Kernel: `4683cd2e3556448295e03a216a3a7fc6e8bbc474`.
- Host and radio libiio: `47a75cbc5e7d24a063b8b54eb531fdba6602b85c`.
- Buildroot package pin: `a3752330bc286c49edf681cf4874a9524c61bfda`.
- PPU: `4e560749aac96b6c53a3fa69c9e4c3893babd306`.
- Shared metadata source: unchanged `3294365ff44da26b261be4a2ccb241b7896d23ad`.
- FPGA and device trees: byte-identical to the verified release FIT.

The candidate replaces only iiOD, libiio, version information and the kernel,
adding modules built for that kernel. `scripts/issue97/package.py` preserves
all other rootfs payloads, ownership, permissions and special files. This is a
release-derived candidate, not a claim of a fresh full Buildroot/FPGA build.
The component hashes and exact DFU/FIT identities are in `artifact.json`.

`bash scripts/issue97/build.sh` rebuilds from the pinned local Linux/libiio
checkouts. Set `PLUTO_TOOLCHAIN_ROOT` to the Linaro GCC 7.3.1 Buildroot host tree
and `BASELINE_DFU` to the verified v0.49 DFU. Optional
`COUNTER_LINUX_SOURCE`/`COUNTER_LIBIIO_SOURCE` select clean source checkouts.
`COUNTER_BUILDROOT_DL` stages the locally generated source archive for the
updated package hash. The local source commits and archive are not published
GitHub release assets; use the local source paths until publication is arranged.

Install the matched PPU runtime from its isolated checkout:

```sh
scripts/install_native_libiio.sh --uv-bin /absolute/path/to/uv \
  --metadata-abi 3 --source-directory /absolute/path/to/libiio-issue-97
```

Open `IioRadioDevice` with `expected_metadata_abi=3`, configure the
`AD9361_1R1T_TARGET_PROFILE.rx_layout_expectation`, and explicitly pass
`counter_only=True` to `begin_metadata_capture`. Configure sampling rate and
analog bandwidth independently: the 60 MS/s tests use 50 MHz analog bandwidth.
`scripts/issue97/public_capture.py` is the executable public-API example.

## Qualification scope

- Exact release baseline: physical 1R1T paired HOLD fails with errno 95 and no
  frames at 2.5/5 MS/s. The same device in physical 2R2T passes RX0 transfer.
- Twelve native suites pass, including real provider dispatch, malformed
  admission, full-width counters, corruption, rebase, layout, queue/transport,
  paired metadata and cleanup tests. PPU: 162 tests pass.
- Physical 1R1T candidate: 5 frames at 2.5/5 MS/s and 30 frames at 30/60 MS/s,
  each with 1,000,000 complex samples and exactly 50 DMA buffers, no gaps.
- A 100-frame 60 MS/s run with a two-second consumer delay reports 229,000,000
  missing samples. Every reported gap independently equals the difference
  between adjacent delivered intervals.
- Wrong rate, automatic gain, decimation and paired HOLD on 1R1T reject with
  errno 95. Rate, LO, bandwidth, gain mode, gain, timestamp writes and a second
  counter owner reject with errno 16 while capturing.
- Abrupt client termination and a forced transport timeout while the lease is
  active both permit subsequent capture and restore timestamp/settings state.
- Normal close restores timestamp control. Forced iiOD death restores the
  kernel lease and allows LAN capture after supervisor restart.
- Physical 2R2T RX0, RX1 and dual RX all pass HOLD and AUTO at 5 MS/s.
- The actual HDL packer and vendor XPM timestamp FIFO pass a CI16/prefix
  scoreboard across continuous, intermittent and randomized valid patterns,
  including a low-word counter wrap (1,511 words, 189 timestamped frames).
  Vendor assertions emit startup/reset warnings before valid input; these
  simulations do not constitute a clean assertion run or exhaustive DMA proof.

These results establish finite 60 MS/s capture and observable loss, not
sustained lossless 240 MB/s delivery over Ethernet. No RF stimulus was emitted;
this is digital framing/control qualification, not analog RF quality testing.

The existing v0.49 FunctionFS/supervisor path leaves USB unbound after SIGKILL
of iiOD; the targeted test manually rebound this radio's gadget. LAN capture
and the counter lease recovered automatically. This pre-existing USB daemon
restart limitation remains outside the counter-mode implementation.

Component patches are preserved in `patches/` for review against the source pins.
The exact candidate DFU and full private qualification logs are in the isolated
worktree `build/` and `evidence/` directories, respectively.
