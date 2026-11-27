# v0.64 continuous 24-frequency scan

Protocol 6 repeats Ch1-X, Ch1-Y, Ch1-Z through Ch8-Z at 10 MS/s, 8 MHz
bandwidth and dual RX. Each complete window contains 200,000 samples per RX
after at least 200,000 source-counter ticks of guard. The kernel owns 24
calibrated profile images and replaces the eight resident slots. Receipts bind
IQ to the plan, logical target, physical slot generation and verified IF.
Existing v5 and v5M wire formats are preserved.

The full-build graph is `manifests/position-scan-v064-source.yaml`. The shipped
image replaces the kernel, installed iiOD and matching libiio in the published
v0.63 parent. `package.py` verifies parent SHA-256, source commits, ARM binaries,
the complete extracted kernel/rootfs, FIT hashes and every protected property.
The release includes the exact kernel configuration and build identities.

Run kernel driver/deadline harnesses, all eight native and ASan/UBSan device
suites, the actual iiOD parser regression, host/tracker suites and ARM builds.
Run the firmware gate and packaging tests before candidate qualification.

```bash
python3 -m unittest discover -s scripts/v064 -v
scripts/check_tandem_release_offline.sh oracles
scripts/check_source_graph.sh manifests/position-scan-v064-source.yaml
python3 scripts/v064/package.py --help
```

Use the pinned host sources with the verified ABI3 native host runtime. The
tracker command writes native IQ chunks, a separate position checkpoint and
binary receipts. Capture and restoration share the station radio lock.

```bash
python -m leo.cli.position_scan --host 192.168.1.15 \
  --serial 104000b29905000e17000800065934759d \
  --root /absolute/capture/root --run-id position24 --duration 30
python -m pluto_plus.position_scan_verify /absolute/capture/root/position24/wire
```

The independent checker verifies hashes, counts, profile/IF/generation identity,
timing and terminal accounting. The authorized cabled bench fixture is TX2 ->
30 dB attenuation -> splitter -> RX1/RX2. It supplies one source IF per capture,
with a distinct DDS offset at each target. Run all 24 in RAM and after flashing.

```bash
python scripts/v064/qualify_tones.py --output /absolute/evidence/tones \
  --tx-gain-db -30 --duration 5
```

Fixture setup and cleanup run inside the recorder's shared lock. The oracle
requires correct frequency, no clipping, adequate SNR, coherent receivers,
stable levels and repeated slot generations. Cleanup verifies muted TX and
restored LO, bandwidth and powerdown settings.

`deploy.py` requires the exact physical USB path and serial, attests the RAM
return and verifies unchanged QSPI. A boot may change the Ethernet MAC. Reattest
it over USB before refreshing the LAN neighbor entry. Preserve each lifecycle
receipt and reconcile an ambiguous transition before another operation.

`deploy_lan.py` requires exact-image RAM, saved-IQ/tone, STOP, interruption,
legacy-v5 and ordinary-RX evidence bound to the same radio and image. Return to
the known-good persistent v0.63 runtime before the guarded firmware-only update.
Verify flash readback and fresh-boot identities, then repeat the scan checks.
Publish the SHA-256-qualified image with source/build/qualification manifests,
representative IQ and rollback instructions. Verify downloaded release assets.
