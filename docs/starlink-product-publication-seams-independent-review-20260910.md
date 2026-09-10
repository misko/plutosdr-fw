# Independent sampled-READY / publication-only seam review

Read-only review of the direct agent's additive primitives and offline tests.
No source edits in that tree, HDL execution, vendor tools or physical claim.
The separate P1 controller-preconditions note remains unchanged. This review
does not qualify a production-top connection or broaden current-fault waivers.

Final disposition: no remaining source-review blocker for this bounded seam.
Owner original65756 ended0 with **2752 PASS in78.64s** (1308 new +1444 unchanged).
I read its terminal and all11 targeted behavioral-mutant failure receipts.
Parent original97763 subsequently independently passed2752 in78.61s and
reported an audit of80 manifests/804 entries,96 exact bank rows and the final
graph/routes/mutants. That independent execution is distinct from my review.

## Exact RTL reviewed

Read-only tree: `/tmp/starlink-rom-prefetch.j829ht/fw`, HDL nested. Final tested
FW `eba403dc38b7a0d5a5634a4f76cb0bf78a3d7ae9` and HDL
`1703e90347b607219d9c714c2cce698deea6ab9d`, independently read from Git.

- Canonical bank remains `starlink_pss_epoch_sealed_bank.v`, SHA256
  `d9c2382f9087ccd2088fa5a5d3fed5c6fe885359d6d4c367ed2ea81ce099d9f6`.
- New `starlink_pss_epoch_sealed_publication_bank.v`, SHA256
  `76d6985aa2148776ee1e834307066575d269878dc2c32cffd2bdbb87f2c5a490`.
- New `starlink_pss_product_sealed_publication_interface.v`, corrected SHA256
  `03c37b96aa77562c9f544b0ff4604e944a7b986677703fc546543caa42718f1f`.
- Its old interface boundary is unchanged SHA256
  `5e060a23903641c8f0c0ec7a0afae22428d1ad15829d1af9985ca0a662de5669`.

## Findings and disposition

1. **READY defect found and corrected before final evaluation.** Earlier issuer
   `e3261cdce4f52c5557893f46ac15e9665731aebedf5476fb48e44298a763bc77`
   used actual sampled READY A without advertised capacity C in its offer
   marker. With producer ownership, issuer-only reason Q set, bank reason Q
   still zero and inner bank capacity1, forced A1/C0 could produce a private
   take despite the diagnostic. Corrected option1 requires both A and C;
   option0 retains the literal original marker. CASE203 constructs precisely
   this mixed-reason state; its missing-C mutant checks the would-take edge,
   not a full bank where inner capacity already prevents the bug.

2. **Publication-only routing matches the approved cut.** P uses the same eight
   logical cause categories as live faults. Only checked_seal/publish gain a
   current P veto; the existing reason-Q recurrence merges `{P,8'b0}`. Original
   errors_now, local_current_clean, certificate, read VALID and release remain
   literal. Adding P to local_current_clean would reconnect release through
   reader validation to input certification; a specific restored-backedge
   mutant covers that route. No register/RAM/DSP declarations were added.
   Cause categories do not distinguish which of the two routes asserted them.

3. **Current downstream protection is separate, not inferred from bank Q.**
   CASE205 injects P while ACK capacity1, bank reason Q0 and bank_live0. The
   real result guard's independent current external fault must prevent actual
   ACK. Removing that caller fence permits the exact forbidden edge and must
   fail. The bank-level tests intentionally allow a read, certificate or
   eligible release on P's first edge, then require reason-Q quarantine.
   Those private bank events are not a healthy downstream publication claim.

4. **A receipt-strength gap was reported and narrowed before freeze.** The first reviewed
   tests accepted generic `PUBLICATION_BANK_`/`PRODUCT_SEAM_` plus `PASS`, rather
   than matching the requested profile and fields. Wrong-profile or bare
   generic PASS text could satisfy that check. Helper `d9677454` added exact
   profile/argument terminals and missing/wrong/duplicate, bare, zero-count and
   late-error controls. Those changes are source-reviewed. The parser still
   parses but does not validate read-count/reason values; the parent explicitly
   chose the HDL assertions plus a separate saved-log value audit instead of
   additional source changes. This is a declared layered evidence boundary,
   not a claim that the parser independently validates every printed field.

5. **The new positive ancestry control exposed a source-alias selector error.**
   Original14624 ended **2749 PASS / 1 FAIL**, not 2750 PASS. The saved VVP's
   three `publication_faults` naming aliases all directly reference the same
   L driver; connected sinks refer to that driver, not the alias IDs. Thus the
   positive seal-cone check failed, and the earlier negative source exclusions
   were insufficient too. The full graph's acyclicity and three cycle-mutant
   results are separate from this failed source-selection claim. The approved
   repair is source aliases to their immediate drivers only, with connected
   and disconnected controls; do not use the entire source ancestor set or
   alter the graph parser. Final helper `db0d31b2` implements exactly that
   repair. Its connected/disconnected fixtures deliberately share upstream
   state, so broad ancestry would fail the disconnected control. Both source
   exclusions and required seal/publish connectivity now use actual drivers.
   The complete parser remains unchanged at `ea5179fc`.

## Test/source review scope

Fully read `tests/starlink_oracle/test_product_publication_seams.py`, both
`product_publication_inverse/{bank,issuer}.patch` files, and HDL test files
`tb/tb_starlink_pss_publication_bank.sv` and
`tb/product_publication_seam_cases.svh`. Whole-body inverses restore the fixed
original sources and reject unrelated body additions. The register-declaration
comparison independently checks the claimed zero added logical state.

Directed controls cover missing A/C, masked raw VALID at READY0, X/Z sampled
READY, current seal/publication/reason loss, internal state updates bypassing
the public veto, and the independent current ACK fence. Default-seam option0
keeps the sealed adapter/bank active but poisons only the unused new pins;
actual arithmetic READY stays untouched. Original legacy branch bytes are
covered by whole-source inverse, not mislabeled as a newly executed legacy
receiver. The new helper also freezes its two imported policy dependencies.

Read the older retained graph receipts at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-publication-seams-v3.P2Rpn7x4`:
base3478 nodes/38 LS nodes is acyclic;
all three separately restored paths have cycles (bank-live, local-current,
read-VALID). This is a read of saved evidence, not an independent traversal or
execution, and not the later final source's graph count. The real certificate
coupling CASE206 exercises a consumer-beat event with received=2: useful graph
and quarantine evidence, not a naturally reachable full-P1 phase proof.

Source-frozen failed14624 inventory, independently rehashed by this review:

- Test helper: `d96774540520db6129058c3c8385e83b45401e7541f5acbf173ef0853db0a38b`.
- Bank bench: `1daa90dd287cad0db74259007b8c12d16e223a13ef7bc6be2f51f0b9cd59c2a5`.
- Seam include: `322181754666e8e0b3048be0bc65939164667b897365ddd1772cd7210615c10d`.
- Bank inverse: `55f21a92618c7705016bcdce58a60d17d47cfb7e62094c33944d32454b8bcd27`.
- Issuer inverse: `6929652c8a971a4230a7d4459cf4c9ce10a52c8d31bdb9b7c796d78aded9ce0c`.
- Both RTL hashes remain those listed above.

Final helper SHA256 is
`db0d31b2e1b8f200887361bfc4044c04eb0759111fb9f5b4ae286991752d1374`;
the other six files above remain identical. The full d967→db0d change was read:
one immediate-driver selector, its use, and two tiny route witnesses. No
receipt-value policy, stimulus, RTL, numerical or fault-assertion changes.

Final evidence read at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-publication-seams-final-v3.iNkUV3PJ`:
graph3488 nodes/38 LS nodes/no cycle; all11 behavioral mutants reach their
specified fatal; CASE206 prints received=2. Terminal log SHA256
`21833d64db997a506d698a0efd8173754555667b3bea3fc04786bda5d855d447`,
JUnit SHA256
`4900d455e0e146e468d90ff513369f528ba247523e63a27aced6ca937f9cdab1`.
These are saved owner receipts, not my own execution. Prior failed14624 and
its d967 source remain intact. The parent's completed independent repeat is
separate from this review.
No vendor/actual FFT or P1 top execution is authorized or claimed by this note.
