# v0.63 multirate continuous-scanner qualification

On 2026-10-22 the exact image was RAM-qualified on development radio
`104000b29905000e17000800065934759d`, then persistently installed and
reboot-checked on `192.168.1.15`, `192.168.1.18` (serial
`1040007c4a94000211000b009186843ef2`) and `192.168.1.20` (serial
`1040005e0b100007100010000bf33a5d4d`). All three returned
`v0.63-plutoplus-spf-continuous-fast-scan` with the exact installed binary
hashes below and muted, powered-down TX. The guarded updater verified the FIT
readback and protected flash regions on all three boards.

| Artifact | SHA-256 |
| --- | --- |
| DFU | `3715beff0ab6d2060437729e1ec82fd672fd475989e4295943715147c39db04b` |
| FIT | `2d87ff9d79724f4452b6526de7d39656905fb35efd84bb4c57027299efd0b13e` |
| Installed iiOD | `c1d596d5b6b04e53dc0e864b4a5c933856347c2164f93c06222f2df6e2972bde` |
| Installed libiio | `1271d7ca57dc98bb03c95aad308bca51f5a45c7e4a106392ad6ef11c346bc8e6` |

The device source is `6162275af8ec4622dc42a53307d6f5a65ed8840f`.
The updated PPU companion is `3fdc4aaa2fe4111cc589a1368fd33398b22068df`; the existing ABI3 native host runtime remains
`7639fc9b6c01336e1451f4f58ccf66e30a22388d`. The firmware and installed iiOD
are bound by their own hashes. The native library's cached compatibility git
string remains the parent `e2ea69c`; `/opt/VERSIONS` records the exact new
scanner source. The new code changes daemon scan handling, not library APIs.

| RX-only exercise | Complete windows |
| --- | ---: |
| Development RAM, dual RX, all five rates | 406 |
| Extended dual RX, 5/10 MS/s, 100,000-sample DMA blocks | 513 + 513 |
| Single RX, 5/10 MS/s | 65 + 65 |
| Persistent .15, dual RX, all five rates | 406 |
| Persistent .15, existing eight-target IF plan, 5/10 MS/s | 129 + 129 |
| Persistent .20, existing eight-target IF plan, all five rates | 645 |
| Persistent .18, existing eight-target IF plan, all five rates | 645 |
| Original v0.62 host on persistent .15, 2.5 MS/s | 33 |
| Legacy finite v3 followed by ordinary RX | 14 + 32,768 ordinary IQ bytes |

Independent readback of **3,516 saved continuous windows (3,384,200,000
bytes)** verified sample counts, hashes, visit/target order, no missing support,
minimum post-recall guards, terminal accounting and settings restoration.
Every retained COMPLETE window covered exactly 20 ms, with a guard of at
least 20 ms in the source-counter domain. All sessions had zero skipped,
invalid or cancelled visits. Median eight-target sweeps were approximately
352–364 ms on the development plan; detailed per-cell timing is retained in
`independent-iq-final.json`.

The initial development plan used 1.80–1.87 GHz in 10 MHz steps. The existing
radio20 IF plan was then exercised after persistent installation:
959687498, 1190312500, 1209687498, 1440312500, 1459687498, 1690312496,
1709687500 and 1940312500 Hz. These are eight explicit IF targets; no RF
identity or LNB polarization is inferred from them.

The complete firmware offline gate passed 1,526 tests (five hardware tests
deselected), both kernel Fast Lock regression harnesses and all tandem HDL
testbenches. Eight native scanner suites and eight ASan/UBSan scanner suites passed,
including 20,000 simulated ordered visits at each of five rates across counter
wrap and bounded-history reuse. ARM build/install, seven package-integrity
tests, repeat byte-identical DFU/FRM packaging, 25 firmware routing/tooling
tests, source-graph validation and the host's 30 focused tests passed. The
host full offline suite passed 5,013 tests with 14 explicit opt-in skips;
GitHub companion CI also passed on Python 3.11, 3.12 and 3.13.

Retained preflight incidents: an SSH check initially used a USB-only trust
file for LAN and failed before acquisition; a simultaneous same-radio test
was rejected by the per-serial lock; persistent installation from RAM first
refused an identical runtime version, so the radio returned to its persistent
v0.60 baseline before the successful guarded update. No failed preflight
performed a firmware write. Stale ARP entries were cleared after reboots.
The first broad offline run encountered local group-writable verifier files
and omitted sparse-checkout Linux fixtures; those environment issues were
corrected before the final run. A local Linux clone hit host disk pressure;
only this task's build/clone artifacts were moved to bulk storage.

This qualification covers native 1.25, 2.5, 5, 7.5 and 10 MS/s continuous
scans, bounded receive sessions and software-reboot persistence on these three
radios. The previously documented .17 endpoint was unreachable and was not
updated. It does not establish every RF transition, physical settling minima,
Starlink detection sensitivity, multi-day reliability, physical cold boot,
or rates above 10 MS/s. The inherited finite scheduled 10 MS/s timeout
limitation is not claimed fixed. No RF transmitter was enabled for this work. Ordinary RX also returned 32,768 bytes on each radio after the
final scan checks.

Detailed evidence is under `/srv/bulk/leo/continuous-scan-v063` on the build
host and is packaged explicitly for release; credentials and SSH trust files
are excluded.
