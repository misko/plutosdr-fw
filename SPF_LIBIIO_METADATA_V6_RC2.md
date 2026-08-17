# LibIIO frame-metadata v6 RC2

v6 RC2 is a RAM-boot-only candidate for issues #32 and #33. It is not eligible
for flash installation until the hardware gates below pass on both Micron and
Winbond boards.

## Root cause and containment

### #32: board reboot after repeated metadata capture

The reports prove a full Zynq reset, but the previous firmware could not retain
the final kernel or userspace messages across that reset. The metadata sampler
also used an unbounded `pthread_join()` during stream close. That is a confirmed
hang defect, but the evidence available in #32 does not prove whether the final
board reset was caused by this path, a wider kernel stall, or power integrity.

RC2 therefore fixes the known hang and makes the remaining reset diagnosable:

- metadata sampler teardown is bounded to 500 ms;
- an unsafe timeout exits only the owning daemon before state is freed;
- iiOD is supervised and restarted without rebooting Linux;
- one MiB of reserved ramoops memory retains kernel-console and userspace pmsg
  records across watchdog resets;
- the reserved region is below the FPGA load address and outside U-Boot's
  high-memory relocation arena;
- each boot and iiOD generation is recorded for correlation.

### #33: blank serial on Winbond W25Q256

`S23udc` previously scraped `SPI-NOR-UniqueID` from dmesg. The kernel emits that
line only for the Micron/ST implementation, so Winbond boards received an empty
serial. Hashing that empty line also produced the repeated `00:e0:22:ad:c8:3b`
host MAC.

RC2 exposes the W25Q256JV factory UID through the SPI-NOR sysfs group after the
existing SFDP discriminator proves the part is JV rather than FV. Userspace
keeps the historical Micron serial unchanged, otherwise encodes the eight-byte
Winbond UID as `winbond-<16 lowercase hex>`. Missing, malformed, all-zero, and
all-ones identities fail closed before USB is bound.

## Red/green gates

| Gate | Red condition reproduced | Green acceptance |
|---|---|---|
| Identity fixture | No Micron log line with a Winbond UID | Stable `winbond-…` serial; invalid UIDs rejected |
| Legacy identity | Micron dmesg serial available | Serial remains byte-for-byte unchanged |
| Teardown unit | Worker exceeds bounded join deadline | Timeout is returned in finite time |
| iiOD recovery | Child exits with the teardown status | Supervisor records and restarts it; board stays up |
| Kernel build | New SPI-NOR and pstore code enabled | ARM objects and Pluto DTB compile |
| Source graph | Any ref is missing or differs from its pin | Every immutable ref equals the manifest commit |
| #32 soak | Repeated open/capture/close plus injected iiOD exits | No boot-ID change; iiOD generation advances |
| #32 reset forensics | Forced watchdog reset | Previous console/pmsg records appear in `/sys/fs/pstore` |
| #33 hardware | One Micron and one W25Q256JV board | Nonempty unique USB/IIO serials and locally administered unique MACs |

The first five gates are automated before packaging. The final three require
RAM-only hardware testing and are promotion blockers, not RC build blockers.
