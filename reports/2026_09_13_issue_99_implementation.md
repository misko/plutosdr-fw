# Firmware #99: implementation and verification evidence

Status updated 2026-09-15: **conservative candidate deployed on `.14`; update,
subsequent update, warm boot, rollback/reinstallation and live oversize refusal
verified, including QSPI power-on cold return. Extended-range qualification remains
pending.**

See [the deployment evidence](2026_09_15_issue_99_deployment.md) for the corrected
updater and current artifact hashes, and [the current plan](2026_09_15_issue_99_plan.md)
for remaining qualification. The original September 13 build evidence below is
historical; the current exact artifacts are in `issue-99-candidate.json`.

## Result and scope

The persistent updater and release packager refuse any payload or erase footprint
above physical `0x01000000`. With the supported firmware partition beginning at
`0x00200000`, the largest allowed FIT is 14,680,064 bytes. The incident's
14,744,943-byte FIT is refused before any persistent mutation. The FRM's 33-byte
trailer is validated and excluded from that calculation.

The candidate contains the repaired kernel and updater while preserving the
published v0.50 FPGA, all three device trees, and radio userspace. Its FIT is
**13,008,423 bytes**; its exclusive erase end is **0x00e70000**. This leaves
25 complete 64 KiB sectors below the conservative physical limit. The artifact
is an audited overlay of a verified release, not a full Buildroot/FPGA rebuild.

The machine-readable `issue-99-candidate.json` beside this report records all
artifact hashes, the rootfs overlay, packaged-DT cross-check and component pins:

| Component | Commit |
|---|---|
| Linux | `2378b1c3b3f0326beff1fecdda4059e095c28648` |
| Buildroot updater | `bedc18df1b45b3f4079149f9903a9b243053f096` |
| U-Boot | `61dff5dff655a62ce3aecec749595ac4f1ca6b51` |

The rebuilt U-Boot is a separate bench artifact. It is **not** installed by the
candidate FRM, and its source hash is not evidence about a device's installed
bootloader. No extended-range qualification records ship.

## Implementation

Linux selects EAR banks using checked readiness, WREN when required, the register
write, completion, exact register readback and WRDI cleanup. It caches only a
verified selection and invalidates uncertain state. Winbond support uses SPI-NOR
manufacturer identity and the `ef4019` part fixup, avoiding the unrelated CFI
Winbond constant `0xda`. Other Winbond part IDs do not inherit this capability.
Existing AMD, ST, Macronix and PMC opcode/WREN behavior has regression coverage.

The production MTD read/program/erase paths split at bank boundaries, propagate
selection/data errors and support both spi-mem and legacy callback test adapters.
Initialization/resume and orderly shutdown establish or attempt verified bank
zero. Stacked reset restores the caller's chip-selection flags. Read-only sysfs
capacity/addressing fields report the selected implementation; they grant no
write permission.

Zynq QSPI aborts a failed command/address/dummy/data phase immediately, disables
and synchronizes interrupts before freeing buffers, deselects CS and quarantines
the controller after an incomplete operation. Subsequent operations return EIO.
This intentionally requires controller reinitialization/recovery; an uncertain
FIFO must not be reused. A shutdown bank-reset failure is logged and cannot
promise to prevent an externally forced reset or power loss.

U-Boot's active `spi_flash.c` verifies bank-write readback and invalidates a failed
selection. A bank error after a successful first read chunk now returns the actual
error and frees the command buffer. Common write errors release the SPI bus.

Both SSH and mass-storage firmware entry points use one locked transaction.
It stages and validates FRM/FIT data, discovers named sibling MTD partitions and
physical capacity, checks protected layout and environment format, and writes
through checked `flashcp` on the character MTD device. Boot and NVM digests must
match before environment mutation and afterward. Only `fit_size` may change in
the parsed environment. Failures propagate, suppress reboot, and retain private
post-dispatch diagnostics. A refused mass-storage batch cannot continue into
boot/config handlers. Mixed firmware/boot images are refused before writing.

Standalone legacy `boot.frm` installation is not a qualified bootloader migration
route. Bench migration must use the separately identified recovery path below.
Concurrent NVM changes may conservatively stop an update at its integrity check.

The Makefile FRM rule and already-built release packaging both enforce the same
range helper, using explicit Pluto/Sidekiq layout profiles cross-checked with
packaged device trees. Full-partition RAM/SD recovery artifacts remain possible,
but a `.dfu` suffix alone does not establish a volatile destination.

## Verification performed

| Verification | Result |
|---|---|
| UML KUnit, production EAR/MTD code | 7 cases passed |
| Updater, active U-Boot C, controller C and release/source tooling | 61 tests passed |
| Target ARM BusyBox updater fixtures and complete candidate, under QEMU | 34 tests passed |
| ARM `fdtget` and `dumpimage` with candidate rootfs libraries | Passed |
| ARM kernel, modules, DT build and U-Boot build | Passed |
| Packaged DT layout and conservative erase span | Passed, all 3 DTs |
| Repeat build using the recorded recipe | FIT and FRM SHA-256 identical |
| New source-lock tags, remote pins, gitlinks and Buildroot recipes | Passed |

The negative-control flash model reproduces the misleading logical readback:
an ignored Winbond bank write directs upper-bank data onto physical boot bytes,
while the same logical read returns the input. Independent physical inspection
detects damage; the repaired production path rejects that ignored selection.
Fault tests also cover partial read/program/erase, WREN/EAR/readback/WRDI failures,
stale-bank initialization, parallel read mismatch, stacked reset, controller
phase timeouts and cleanup, mixed update batches, and the complete incident size.

QEMU verifies ARM userspace compatibility and shell behavior. It does not emulate
this Zynq QSPI hardware. Fake SPI tests do not qualify silicon, four-byte paths,
every parallel/stacked topology, installed boot commands, persistent DFU, warm/cold
boot, or recovery reliability. Existing kernel host-tool warnings and FIT unit
address warnings remain visible in the build logs.

## Reproduce locally

Use an initialized checkout at these component pins, host `dtc`, U-Boot tools,
the existing Linaro Buildroot ARM toolchain, pytest, BusyBox and qemu-user.

```sh
PLUTO_BUILDROOT_HOST=/path/to/buildroot/output/host scripts/issue99/build.sh
python3 linux/tools/testing/kunit/kunit.py run \
  --kunitconfig=tools/testing/kunit/configs/spi_nor_ear.config \
  --build_dir=.kunit-ear --jobs=8
python -m pytest -q tests/test_flash_safety.py tests/test_flash_safety_candidate.py \
  tests/test_uboot_flash_banks.py tests/test_zynq_qspi_failures.py \
  tests/test_firmware_release_tooling.py
python scripts/issue99/verify_arm.py
```

Build outputs are in `build/issue99/candidate`; local evidence logs are in
`build/issue99/evidence`. The build verifies the immutable baseline SHA-256,
retains its embedded kernel configuration except LOCALVERSION, pins build time,
and refuses dirty component trees. The published base DFU hash is
`435a26369018e86ee66262b79c32895dbaaacef510a1efb71c566d6409555344`.

`manifests/flash-safety-v1-source.yaml` locks the new source graph. PR CI checks
it against the current gitlinks and retains historical release-lock checks.
The dedicated GitHub-hosted flash job runs the host C/updater tests and KUnit;
it has no radio access. The protected main build/release route still names the
published counter release and must be advanced as part of qualified promotion;
this draft does not change that release or bypass its checks.

## Deployment and qualification status

Completed on the dedicated `.14` Winbond target by the PPU hardware task:

- Incident recovery, full physical backup, and QSPI cold-return acceptance.
- Exact #99 candidate SD/RAM boot with normal init bypassed and RF inactive.
- Candidate Linux full 32 MiB read matching independent SD physical capture.
- Separate erase/program tests of 64 KiB sectors at `0x00ff0000` and
  `0x01000000`, independent placement checks, restoration, and full independent
  comparison with the recovered baseline.
- Normal QSPI power-on return to the original recovered GLRT image, protected
  regions and FIT verified, IIOD running and IIO buffers disabled.

These results cover one target and separate sector operations. They do not prove
one write call crossing the bank boundary, the persistent candidate's updater,
the repaired U-Boot running on hardware, or a crossing FIT boot. The FRM does not
install the rebuilt U-Boot. Production limits remain at physical 16 MiB.

Remaining work follows [the current plan](2026_09_15_issue_99_plan.md): land the
PPU BusyBox backup fix, integrate the complete candidate writer identity, complete
bounded driver and bootloader qualification, test conservative persistent
bootstrap and rollback, then test a crossing FIT through a reviewed bench route.
Only matching hardware/software evidence may enable a shared extended-range
qualification record. Generic release-profile approval is not flash qualification.
