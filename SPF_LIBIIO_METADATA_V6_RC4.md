# LibIIO frame-metadata v6 RC4

v6 RC4 is a RAM-boot-only candidate for issues #32, #33, and #34. It must not
be installed in serial flash until all four attached Pluto+ boards pass the
hardware matrix below.

## Changes from RC3

### #34: fail-closed TX state at boot

Hardware testing found that RC3 initialized each active AD9361 TX channel at
`-10 dB`. DDS sources were disabled, so this was not proof of an emitted signal,
but it was not the requested safe starting state.

RC4 sets `adi,tx-attenuation-mdB = <80000>` in the shared Pluto device tree, so
the AD9361 driver initializes active TX paths at exactly `-80 dB`. Before the
USB gadget is exposed, a second independent startup gate:

- locates the AD9361 PHY and DDS IIO devices;
- writes zero to every DDS raw control and verifies the readback;
- writes `-80` to every exposed TX hardware-gain control and verifies it;
- returns the radio to RAM-DFU recovery if TX mute cannot be verified.

This is a firmware-controlled default, not a permanent lock. An authorized
application may deliberately set another gain after boot.

### #33: W25Q256FV identity and recoverability

RC3 enabled Winbond UID reading only when SFDP identified the shared `ef4019`
JEDEC part as W25Q256JV. The attached blank-serial radio reports W25Q256 but
follows the FV path, so RC3 had no sysfs UID. Its fail-closed identity gate then
withheld the whole composite USB gadget, including ACM and Ethernet, making a
RAM-booted radio appear to disappear.

RC4 enables factory UID opcode `4Bh` for both FV and JV variants. FV global
4-byte-address mode uses the required fifth dummy byte; JV keeps four dummy
bytes with dedicated 4-byte opcodes. A hardware red on the attached Zynq board
showed that its QSPI controller deliberately bypasses SFDP and therefore never
runs the part's BFPT hook. RC4 installs the common UID reader from the
unconditional post-SFDP hook while retaining BFPT only for FV/JV addressing
discrimination. A source regression test covers that Zynq-specific path.

Invalid identities remain rejected, but a startup identity failure now exposes
only an explicitly labelled, per-boot network/ACM recovery gadget. USB-IIO and
direct-SDR functions remain withheld, so the unit is reachable for diagnosis
without presenting an unsafe radio identity.

The same board carries a newer 2023 U-Boot whose stored `adi_loadvals` has a
malformed `test -n ${attr_val} = ad9364` condition. With the redundant
`attr_name`/`attr_val` compatibility override present, every boot rewrites
`mode=1r1t`. Removing only that redundant pair while retaining
`compatible=ad9361` makes `mode=2r2t` survive a real U-Boot/RC4 RAM boot; both TX
gain controls then initialize to `-80 dB` and all eight DDS controls to zero.

### #32: reset containment and evidence

RC4 retains RC3's bounded metadata teardown, iiOD supervision, generation and
boot correlation, and ramoops reset evidence unchanged.

Hardware qualification also exposed an independent receive-path failure. The
Pluto kernel requested a 256 MiB contiguous-memory (CMA) pool, but the fixed
ramoops region at 239 MiB splits the DMA-addressable placement window. Boot
therefore reported `cma: Failed to reserve 256 MiB` and `CmaTotal: 0 kB`.
Direct receive then attempted fragile order-10 allocations for each 4 MiB IIO
buffer, producing `__alloc_pages` warnings and libusb timeouts. RC4 reduces the
default pool to a 64 MiB hardware-validation candidate, which leaves ample
capacity for concurrent IIO blocks while fitting below the reserved pstore
region.

Four-board stress then reproduced a separate failure on the front-port radio:
the host lost the physical USB link during a finite 4 MiB bulk transfer while
Linux on the Pluto, Ethernet, the boot ID, and both gadget processes remained
alive. Because FunctionFS did not deliver `DISABLE`, the direct-USB worker kept
32 MiB of CMA indefinitely and the otherwise healthy direct-IP receiver
returned `-EIO`. Killing the USB worker released CMA and the existing
supervisor restored the same serial and physical path without rebooting.

The corrected RC4 gadget arms a ten-second watchdog after the last finite DMA
block is submitted and keeps recovery armed until the host explicitly sends
STOP. A short/error completion (including `-ESHUTDOWN`) or a missing STOP
requests the existing supervised UDC unbind/rebind; normal process cleanup
then releases IIO/CMA ownership. This means a host-side link loss cannot strand
DMA ownership or poison direct-IP recovery, including when device-side AIO
completed just before the physical disconnect.
Buildroot now pins the manifest-declared gadget source; the previous RC4 build
configuration incorrectly compiled `ab270f9e` while its source manifest named
`907978b0`.

## Four-board qualification checkpoint (2026-08-17)

CI run [`32002024507`](https://github.com/misko/plutosdr-fw/actions/runs/32002024507)
built and attested firmware commit `e9e675e6dd89b525cdae2dc112b36ee6ce190e9b`.
The RAM-only DFU SHA-256 is
`a92aa9c02cba8292a7f8bb034db455f164cb5428c61ecd14941f70ee45c5763f`.

The exact image completed two independently identified RAM boots on all four
attached radios. On both boots every board retained its serial and physical
USB path, exposed 2R2T, reserved 64 MiB CMA, initialized TX1/TX2 to `-80 dB`,
and initialized all eight DDS raw controls to zero before a host mute command.
The Winbond board retained its static Ethernet address `192.168.1.14`.

| USB path | Serial | LAN |
|---|---|---|
| `3-4` | `104000bac4950008230026001b440a003a` | `192.168.1.17` |
| `3-8` | `1040007c4a94000211000b009186843ef2` | `192.168.1.18` |
| `3-10.2` | `winbond-db620818a328172c` | `192.168.1.14` |
| `3-11` | `104000b29905000e17000800065934759d` | `192.168.1.15` |

Hardware green so far:

- 60 repeated production-size 4 MiB direct-USB lifecycle captures, including
  30 consecutive captures on the previously disappearing front-port board;
- a deliberately omitted host STOP caused automatic watchdog recovery in 12
  seconds: USB devnum `103` became `104`, while path, serial, Linux boot ID,
  Ethernet, TX mute, and healthy CMA ownership were preserved;
- deliberate direct-USB child crashes recovered on all four boards with new
  process nonces, unchanged boot IDs and paths, standard USB-IIO present, and
  three ordered 4 MiB frames after each recovery;
- all 32 ordinary/metadata standard-libiio TCP cells passed at 1, 3, 10, and
  30 MS/s; direct-IP malformed-control and one-frame protocol-v3 gates passed
  on all four LAN addresses;
- protocol-v3 repeated fresh starts and V7 Zarr round-trip passed. One initial
  host time-anchor observation measured 6.76 ms against a 5 ms bound; three
  immediate isolated retries measured 0.55--0.68 ms and the all-four rerun
  passed with a 2.98 ms worst case;
- TX2 physical loopback passed on all four boards with 20 dB declared minimum
  attenuation and a strongest TX setting of `-10 dB`. Cyclic DMA-to-DAC,
  manual-gain tone quality, slow-attack AGC, and final `-80 dB` mute all passed.

Promotion remains blocked, without a radio failure, by two host limits that
require sudo: `usbfs_memory_mb=16` blocks simultaneous four-radio 4 MiB USB
capture, and `net.core.rmem_max=4194304` limits the effective direct-IP receive
buffer to 8 MiB instead of the required 256 MiB for a 16-frame burst. The
labelled network/ACM-only recovery path must also pass an injected identity
failure before persistent installation.

## Red/green evidence

| Gate | RC3 red | RC4 green acceptance |
|---|---|---|
| Boot attenuation | Active TX gain reads `-10 dB` | Every active TX reads exactly `-80 dB` before host services |
| DDS state | DDS disable was assumed | Every exposed DDS raw control reads zero |
| Startup failure | Missing identity leaves no runtime USB interfaces | Labelled network/ACM recovery; RF data functions absent |
| Winbond identity | Zynq SFDP bypass omits `spi-nor/unique_id` | Stable nonempty `winbond-<16 hex>` serial and unique MAC |
| Micron regression | Three boards have stable historical serials | Serial remains byte-for-byte unchanged |
| 2R2T topology | Recovered Winbond board reverted to `1r1t` | Two RX scan paths and two TX gain controls on every board |
| #32 stress | Repeated metadata teardown could reset a board | No boot-ID change; supervised iiOD recovery is bounded |
| 4 MiB RX DMA | Boot has `CmaTotal: 0 kB`; direct USB receive times out in `__alloc_pages` | Boot reserves 64 MiB CMA; repeated 4 MiB USB/IP receives complete without allocation warnings |
| USB link loss | Host disconnect leaves 32 MiB CMA owned and IP START returns `-EIO` | Finite-write watchdog releases DMA and supervised re-enumeration restores the same path/serial |
| Gadget provenance | Manifest names `907978b0`, Buildroot compiles `ab270f9e` | Manifest, immutable source tag, Buildroot pin, and embedded build ID all name `1bbe9f0e` |
| Reset evidence | Cause was lost across reset | Previous console/pmsg survives a forced watchdog reset |

## Four-board promotion matrix

Each board is loaded to RAM only and must pass:

1. exact firmware/source attestation and stable identity across USB and IIO;
2. immediate post-enumeration `-80 dB` TX1/TX2 readback and DDS-zero checks;
3. 2R2T channel enumeration and TX2-to-tee-to-attenuator-to-RX1/RX2 loopback;
4. receive, recovery, standard libiio, direct USB/IP, TX loopback, and stress
   suites without a boot-ID change;
5. labelled network/ACM-only recovery on an injected identity failure.

Any red result blocks promotion and is fixed and retested in RC4. Serial-flash
installation remains explicitly out of scope until the entire matrix is green.
