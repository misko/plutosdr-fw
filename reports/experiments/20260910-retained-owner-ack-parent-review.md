# Retained owner: independent ACK-boundary hardening

Parent wrote independent standalone probes and checked three preserved versions
of the new owner. These are module-boundary control tests, **not demonstrated
reachability in the complete controller**, and do not invalidate the earlier
17-case scripted composition result.

| Version | Ordinary real ACK | Eight invalid coincident controls | Valid pending-receipt + real ACK |
| --- | --- | --- | --- |
| Original`f9f51f68` | PASS | Each fails the no-release assertion | PASS |
| First fence`49b671d0` | PASS | All rejected | Fails: legitimate ACK blocked |
| Final`b6280f6a` | PASS | All rejected | PASS |

Each probe first admits an owner, publishes, observes bank busy, and supplies
matching request/ACK evidence. Negative cases have already consumed their
transfer receipt. At real ACK they add duplicate publication, publicationX/Z,
repeated transfer, transferX, duplicate admission, admissionX, or ACKX. Original
reader_release was1 orX before the reason register updated; all eight original
simulation failures are retained. No false-ACK or top-level exploit is claimed.

The first fence required all other controls zero. Parent also tested a valid
caller that retains its transfer receipt until the real ACK: this passed on the
original owner but failed on that first fence. The final change requires known
event controls and admission/publication0, while allowing transfer consumption
if its receipt is still owned. It rejects already-consumed/unknown transfers
without blocking legitimate simultaneous retirement. No state is added.

Parent reviewed the exact small RTL deltas and independently reran identical
benches on final owner SHA
`b6280f6a894ec120f0e57415d5cc6da7b9e193a65f42b1d7f9789cbdbaa5d648`:
**10 PASS**, including both healthy cases. Each source is pinned and unchanged
after its run. Full composition additionally needs to prove its actual ACK
control ordering; the separate owner's expanded suite is not qualified by
these ten standalone probes.

Recovery:`retained-owner-ack-parent.0Zk354cK` under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Archive`20260910-retained-owner-ack-parent.tgz`:136930 bytes,
SHA`618b1111ca6e3b946428f6463974f8c2567e44774fd11f9c384986c623fe1838`;
tar comparison exited0. Includes all three source versions, independent benches,
replay scripts and all30 compile/run receipts. Original8 invalid-control failures
and the first-fence healthy failure remain failures in their own logs; outer
reproducer success means the expected failure was reproduced, not simulation PASS.
The original-source paths in the first two replay scripts identify the preserved
frozen17 snapshot; its identical bytes are also included as`owner-original.v`.

Final parent JSON SHA
`f693eb010e3cafc4a69db35a33800cd682157d695827850cdf5b751ff5d0f7c8`.
No old runtime, production HDL gitlink, PPU, radio or main branch changed.
