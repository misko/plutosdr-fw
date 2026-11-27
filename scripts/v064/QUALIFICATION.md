# v0.64 development-radio qualification

On 2026-11-27, the exact v0.64 image passed RAM and persistent-flash/reboot
qualification on `192.168.1.15`, serial `104000b29905000e17000800065934759d`.
The guarded updater verified the firmware FIT readback and protected regions.
Installed kernel and userspace identities matched the packaged components.

| Artifact | SHA-256 |
|---|---|
| DFU | `b9aeeb8f4e6e8e88c3b88b8af5d69fd1e7e0ed7b5fb5bb31a22b65eea9e31ddc` |
| FIT | `0529df3dfba4d477f6b9fb23cf73bd658084593f9c3de48080e677f77a9d0980` |
| Kernel | `d4704bf2e99f60c88dc40cdbd743662052cdb88704f0cdfb6e00267b483c033c` |
| Installed iiOD | `ec15cff53ff9d04a663d58cec4c0234230d584a5b5a910de7cd0325e91fd3bf6` |
| Installed libiio | `7cd4d9371569174eba447ef67f5572fe62c0dfc37ff125b90b0dfc840ab9e766` |

| RX exercise | RAM | Persistent boot |
|---|---:|---:|
| Complete v6 windows, including tracker and controls | 3,333 | 3,335 |
| Complete windows in the 24 tone captures | 2,616 | 2,616 |
| Physical IFs verified on both receivers | 24 | 24 |
| Matched dual-RX tone observations | 109 | 109 |
| Actual tracker recorder windows | 651 | 653 |
| Legacy v5 windows across all five rates | 126 | 126 |
| Ordinary RX control bytes | 32,768 | 32,768 |

The cabled fixture was TX2 through 30 dB attenuation and a splitter into RX1
and RX2. Each capture ran the entire 24-target plan at full speed while the
source held one IF with a distinct DDS offset. Repeating for every source IF
proved all 24 tunings from saved IQ, with four or five observations at each
target across repeated slot reuse. Tone evidence is linked to the exact
acquisition counters, requested/verified IF and physical slot generation.
Each complete window also passed the clipping check. Per-tuning power and SNR
are retained, including transitions across the 1.3 GHz gain-table boundary.

The independent checker verified 6,668 complete v6 windows, or
10,668,800,000 IQ bytes, with 200,000 samples per RX and 1,600,000 bytes per
window. Every window had exactly 20 ms valid IQ following at least 20 ms of
guard in the continuous source-counter domain. Terminal totals and host
restoration matched the saved data. The native tracker chunks were separately
reopened and compared byte-for-byte against all wire IQ, receipts, counters,
target identities, checkpoint state and recomputed per-RX powers.

| Source-counter timing | RAM median / p95 / max | Persistent median / p95 / max |
|---|---|---|
| Full 24-target revisit | 1,107.64 / 1,109.96 / 1,111.84 ms | 1,102.72 / 1,105.17 / 1,106.34 ms |
| Valid dwell | 20 / 20 / 20 ms | 20 / 20 / 20 ms |
| Post-recall guard | 20 / 20 / 20 ms | 20 / 20 / 20 ms |

The RAM median spacing between window starts was 46.13 ms. First-target to
24th-target start spans 23 intervals and measured 1,061.15 ms median. Returning
to the same target spans all 24 intervals. The machine-readable timing report
includes counts, minima, median, p95 and maximum for preparation, profile load,
recall/lock, guard, gaps, X-to-Z and revisit timing.

Normal STOP and a SIGINT interruption after IQ delivery both restored receiver
geometry, gains/modes, kernel buffers and inactive Fast Lock. Ordinary dual RX
worked afterward. Final TX gains were -80 dB, DDS was disabled and the TX LO
was powered down. The old v0.63 host passed all five advertised rates on the
new image. The new host rejected protocol 6 against persistent v0.63 before
radio preparation.

The firmware offline gate passed 1,528 tests with five explicit hardware
deselections, the kernel deadline harness, 48 legacy and 88 bank scenarios,
and all HDL simulations. The eight device suites passed native and ASan/UBSan
builds. The actual public parser regression covers negotiation, OPENM,
READSCAN, STOP6 and STATUS6. Host focused suites passed 50 PPU and 41 tracker
tests; C/Python wire fixtures, lint, type checking and lockfile checks passed.
The v0.64 packaging, deployment and fixture suite passed 19 tests.

A clean kernel rebuild reproduced the kernel SHA-256 above byte-for-byte.
The release includes `kernel-reproducibility.json` with the exact toolchain,
configuration, timestamps and debug-path mapping, plus independent IQ reports,
representative tone IQ/receipts and complete short control captures. The source
manifest pins Linux, iiOD, Buildroot, PPU and tracker through immutable refs.
