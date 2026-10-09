# v0.62 development-radio qualification

## Motivation

Release the continuous scanner first. FPGA power acceleration is deferred and
does not contribute any source or bitstream changes to this release.

## Problem

The previously RAM-staged daemon was based on v0.60 and used build-tree
executables. Release evidence must apply to the exact installed pair and the
packaged image retaining v0.61's PLL timeout correction and diagnostics.

## Solution

The image contains clean libiio source
`e2ea69c284f0f1c64efb05c0251bca2ee59932b1`. Its installed ARM iiOD SHA-256 is
`f8555bf2e646b87441b279005ea508689d79b218565a1423d42d718da02198dc`; matching
libiio SHA-256 is
`00a22df5f484055e2ab4db1d18db6f18fb0c44d8eca0d35d85de2cfe4db2bfe2`.
Both were read back after boot and have no embedded RPATH/RUNPATH.

The qualified DFU SHA-256 is
`e933bef47c22ee5671306b210471bc3135e8e37ac7f1b2d10df1d556358e21b3`.
Its FIT body is
`eb04a467e1cfb2dab00055c21699e70584975fe5a736909aad0d851538d3db18`.
Repeated packaging produced byte-identical DFU, FRM and artifact bindings.

## Method

On 2026-10-09 the exact image was RAM-booted on development serial
`104000b29905000e17000800065934759d`. The guarded PPU volatile-firmware path
verified the returned physical USB target, firmware, metadata ABI 3, PHY,
tandem capability and muted TX. Boot ID changed to
`b2b8fe39-aa34-45c0-ba68-3f3f829270a7`. QSPI SHA-256 remained
`27c992a20827fbf64b9c40b44b3bfe782229aaccee7fde7387bd52c2038bb3cb`;
the supported legacy AD9361/2R2T U-Boot tuple also remained unchanged.

| Exercise | Result |
| --- | --- |
| Ordered v5 receive/STOP | 601 complete dual-RX windows; 50,000 complex samples per receiver per window; 240.4 MB; zero skips/invalid/cancelled; restored |
| Recording rotation | 512 + 89 windows across two sealed segments; continuous session/generation |
| Quiet software power | All 1,202 receiver decisions QUIET |
| Five-second TX2/20 dB splitter loopback | 112 complete windows; 14 tone-target windows gave 28 ACTIVE receiver decisions; other 196 decisions QUIET; zero ADC12 rail contacts in tone windows; 100 kHz peaks on both receivers |
| Legacy v3, 2.5 MS/s, 120 ms dwell | 14 complete windows over a two-second scheduled scan; settings restored; subsequent ordinary RX returned 32,768 bytes |

Both v5 exercises used IF targets 1.80 through 1.87 GHz in 10 MHz steps,
2.5 MS/s, simultaneous RX1/RX2, manual RX gain 40 dB and a 20 ms post-recall
guard. The loopback used TX2 gain -30 dB and the user-confirmed 20 dB attenuator
before the splitter. All RF exercises were bounded to seconds. TX gains and
DDS were muted after the tests; the TX oscillator was then powered down.

The host used continuous companion source
`f8150de999777a4720e261c5ac4b8c6db0747572`, together with the receipt-verified
metadata ABI 3 host runtime from source
`7639fc9b6c01336e1451f4f58ccf66e30a22388d`. V5 uses the companion's direct TCP
protocol; public IIO preparation uses that existing native host runtime. This
host runtime is distinct from the new ARM daemon/library installed on the radio.

Eight native daemon suites, eight ASan/UBSan suites, ARM build/install, seven
package-integrity tests and the source-graph check passed. The host companion's
full offline suite passed 5,001 tests, with its 14 explicit opt-in skips, and
compatibility checks passed on Python 3.11–3.13. Independent saved-IQ validation,
timing distributions, build/source bindings and raw qualification receipts are
published as release evidence.

Preflight failures are retained: the newer candidate-ram route required an
absent legacy selector pair; it did not perform a boot. The supported volatile
route succeeded. Its subsequent LAN re-attestation initially timed out because
the reboot changed the Ethernet MAC while the host retained an old ARP entry.
USB re-attestation and clearing that one stale neighbor restored access. An
initial recording attempt over the USB-gadget IP was rejected before activation
by the host's canonical LAN-URI requirement; it produced zero windows. Successful
scan evidence uses `ip:192.168.1.15`.

This is a hardware-qualified development prerelease, not qualification of every
RF transition, LNB, gain or temperature. V5 is fixed at 2.5 MS/s. The guard is
verified in the reported counter domain; minimum physical settling and counter
snapshot age are not independently calibrated. Energy detection does not prove
Starlink identity. FPGA acceleration, 5/10 MS/s v5, long-duration hardware
reliability, physical cold boot and persistent installation are not claimed.
The inherited legacy 10 MS/s scheduling-feasibility limitation remains.
