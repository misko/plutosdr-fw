# Firmware #99: conservative deployment on radio .14

Status on 2026-09-15: the conservative candidate is deployed on `.14`; warm
boot, a subsequent update, rollback/reinstallation, receive sampling and live
oversize refusal passed. Physical power-cycle acceptance passed on 2026-09-15.
This report does not grant extended production access.

## Implemented corrections

PPU integration branch `codex/issue-99-ppu-integration`, commit `a049f54`, includes
main through `9a4dc78` and the earlier BusyBox backup correction. It binds the
new writer's wrapper, implementation/range helpers, command resolution, shell,
dynamic loader and libraries to a reviewed 36-path footprint. Altered or missing
dependencies fail before persistence; the physical limit stays at 16 MiB.

Live preflight also required separating SSH authentication diagnostics from
command output, bounding prompt scanning for large backups, and parsing inactive
U-Boot environment tail bytes according to the reviewed import semantics. CRC
covers the entire environment; backups retain all bytes, and active settings
other than `fit_size` remain protected. Strict default recovery parsing is retained.

The candidate updater used `stat`, absent from the released ARM BusyBox. Buildroot
`857c1a81789be9b0ef6019d844f2670ca7e1a46f` replaces it with `wc -c`.
The ARM verifier now explicitly checks the required BusyBox applet inventory so
host command fallback cannot substitute for that check. Source tag
`flash-safety-v1-source/buildroot-v2` records the correction.

## Exact deployed candidate

Kernel, FPGA and device trees match the previously RAM-tested candidate. The
updater and rootfs source provenance changed, producing new artifact identities:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| FIT | 13,008,423 | `11248f8b028c5f1b09693c7c7ab9dddcbc63a2cb94ffdc4dab65ef8b5bea4562` |
| FRM | 13,008,456 | `1a82a4280731fd9a3b9b634b5c0ab17ced61a1e2353c5349f87530c24ddc5eee` |

Exclusive erase end remains `0x00e70000`. The installed U-Boot is unchanged.
The complete overlay/source/file manifest is [issue-99-candidate.json](issue-99-candidate.json).
The device reports `v0.50-counter-rx-v1-flash-safety-rc1`; use the exact hashes to
distinguish this corrected candidate from the earlier RAM-test artifact.

## Verified live milestones

- UART re-attested the bound Winbond target, QSPI boot and disabled IIO buffer.
  Its current SSH key was verified through UART and pinned privately; stale host
  trust was not bypassed.
- Current boot, environment and NVM bytes matched the recovered baseline. A new
  exact rollback FIT backup matched SHA-256
  `56391f5da4569189bdcbf4e80c2d76553bda8d271d23aa529a1d71728a90a84a`.
- The legacy writer installed the candidate below the conservative boundary.
  Host readback verified the complete FIT, unchanged boot/NVM and only the
  intended active environment delta before reboot.
- Normal QSPI warm boot ran the candidate with normal init. IIOD, device identity,
  disabled buffers, complete FIT and protected regions passed verification.
  Host network IIO context discovery also passed.
- PPU recognized the complete candidate writer footprint on the running device.
- A second persistent update using the new common updater completed. FIT and
  protected checks passed before reboot and again after warm return, including
  comparison of active environment settings with the original backup.

- Rollback through the new updater booted the exact retained GLRT image. Its FIT,
  boot/NVM, active environment settings and IIOD service passed warm-return checks.
- The installed PPU wheel reinstalled the candidate, which passed the same warm
  return checks. A receive-only smoke test captured 1,024 IQ samples (4,096 bytes),
  left buffers disabled and restored the scan configuration.

- A valid 14,680,065-byte FIT was refused by both PPU and the live device updater.
  The latter returned a range error before mutation; no reboot occurred. Full
  32 MiB hashes and the complete host observation were unchanged.
- The live complete image hash is
  `a5fb0a8432d4960d365f57ddd39ac3095314448e2003746a3f464b3976da468c`.
  It matches reconstruction from the independent recovered baseline, candidate
  erase span/FIT and verified environment. A fresh independent SD capture of
  this persistent state remains separate work.

Power-off cold-boot acceptance passed at 14:12 UTC on 2026-09-15. The user
confirmed removing all power, leaving SD removed and normal QSPI selection,
waiting ten seconds and restoring power. The original 30-minute UART listener
had expired, so this acceptance resumed at the running login prompt; an initial
boot transcript is not claimed.

UART identified the bound Winbond target and read reset cause `0x00400000`
(power-on) and boot selection `0x00000001` (QSPI). The boot ID differed from the
final warm-return record. The exact candidate FIT and complete reviewed writer
footprint matched. Boot/NVM bytes and active environment settings matched the
saved baseline with only the intended `fit_size` change. IIOD and network IIO
context discovery passed, with buffers disabled and TX muted.

The complete 32 MiB Linux readback again matched the expected candidate image
hash `a5fb0a8432d4960d365f57ddd39ac3095314448e2003746a3f464b3976da468c`.
The private `cold-return.json` receipt SHA-256 is `413494bc03cc793f428f8b0f0087f5469e1fd5c64826291520e230dcea56f458`.
This completes the conservative deployment's cold-return milestone. It does not
replace independent SD or installed-bootloader extended-path qualification.

## Verification and limits

681 related PPU tests passed; after the bounded-search correction, 147
SSH/setup/bootstrap tests passed, including a real PTY large-output regression.
The installed PPU wheel passed 682 selected tests; all 122 packaged files were
verified. Local `pluto` and `plutod` launchers now select release
`issue99-a049f54`; previous launcher targets are retained in its deployment
receipt. Existing daemon processes were not restarted.
PPU PR CI passed its browser lane and Python 3.11/3.12/3.13 offline lanes.
The corrected firmware passed 34 ARM candidate/transaction checks and 60 host
flash/release/driver checks. Firmware PR CI passed source graph, flash/KUnit,
gadget, CDC and merge-guard checks, plus the broader offline oracle lane. All
checks passed on firmware code commit `199959321`.

Early warm-return checks requested a host key before the new runtime's lazy
key generation was reached over the network. They stopped attestation without
repeating a flash operation; read-only UART attestation resumed afterward.
The existing S45msd HTML substitution emits a sed warning for slash-containing
version labels; the MSD update process starts. This presentation defect was
already present in the preserved release startup script.

Private backups, exact operation journals and UART evidence remain under
`~/pluto-qualification-99-radio14/deployment`. No raw device evidence is committed.
A crossing MTD request, independent SD comparison under the new persistent state,
installed bootloader extended paths, a crossing FIT, and second-sample coverage
remain separate milestones. Production extended writes remain disabled.

PPU installed wheel SHA-256: `ae0cdd47a3c156eb10d983e795d5d15dce86aee6f5e6695b21fd1dfa52f1ae3f`.

Review links: [firmware PR #100](https://github.com/misko/plutosdr-fw/pull/100),
[PPU integration PR #115](https://github.com/misko/pluto-plus-utils/pull/115).
