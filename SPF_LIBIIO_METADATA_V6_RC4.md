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
- returns the radio to RAM-DFU recovery if any check fails.

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
bytes with dedicated 4-byte opcodes. Invalid identities remain rejected, but a
startup identity failure now returns to visible RAM-DFU recovery instead of
leaving the unit unreachable.

### #32: reset containment and evidence

RC4 retains RC3's bounded metadata teardown, iiOD supervision, generation and
boot correlation, and ramoops reset evidence unchanged.

## Red/green evidence

| Gate | RC3 red | RC4 green acceptance |
|---|---|---|
| Boot attenuation | Active TX gain reads `-10 dB` | Every active TX reads exactly `-80 dB` before host services |
| DDS state | DDS disable was assumed | Every exposed DDS raw control reads zero |
| Startup failure | Missing identity leaves no runtime USB interfaces | Unit reappears in RAM-DFU recovery |
| Winbond identity | W25Q256FV has blank USB/IIO serial | Stable nonempty `winbond-<16 hex>` serial and unique MAC |
| Micron regression | Three boards have stable historical serials | Serial remains byte-for-byte unchanged |
| 2R2T topology | Recovered Winbond board reverted to `1r1t` | Two RX scan paths and two TX gain controls on every board |
| #32 stress | Repeated metadata teardown could reset a board | No boot-ID change; supervised iiOD recovery is bounded |
| Reset evidence | Cause was lost across reset | Previous console/pmsg survives a forced watchdog reset |

## Four-board promotion matrix

Each board is loaded to RAM only and must pass:

1. exact firmware/source attestation and stable identity across USB and IIO;
2. immediate post-enumeration `-80 dB` TX1/TX2 readback and DDS-zero checks;
3. 2R2T channel enumeration and TX2-to-tee-to-attenuator-to-RX1/RX2 loopback;
4. receive, recovery, standard libiio, direct USB/IP, TX loopback, and stress
   suites without a boot-ID change;
5. recovery to RAM DFU on an injected identity failure.

Any red result blocks promotion and is fixed and retested in RC4. Serial-flash
installation remains explicitly out of scope until the entire matrix is green.
