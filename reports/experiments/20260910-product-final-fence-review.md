# Producer-local product publication: independent offline review

Firmware experiment only; DO NOT MERGE. No receiver promotion or radio access.

The routed ROM-prefetch experiment still fails setup at -1.360 ns. Its worst
reported path starts at product metadata, crosses input checking and reaches
product-bank publication. This alternative changes only the authorization
sampled by the producer's final write; it does not delay the global fault tree.
It remains separate from the inverse sealed-bank/dual-clock alternative.

## Reviewed implementation and limits

Two additive modules default off. The original top, mailbox, input/result
guards, FFT, joiner, ROM and arithmetic remain unchanged. Whole-source inverse
tests restore the exact original modules at HDL
`efc97d8ac92578e1e37eb0bb28c64780b86cf76a`.

The new final predicate retains duplicate-start, sticky input fault, synchronized
source fault, vendor, fast, kernel, overflow, product-bank current/sticky and
result faults. Original global reasons, authorization, handoff ACK and completion
remain literal. No register, RAM, DSP or nominal cycle is added by this cut.
That source-level observation is not a mapped-resource or timing result.

Source review of the actual wrapper and guards supports the conditional argument:
`forward_committed` follows a qualified forward final; closed input cannot have
new framing/delivery errors, but duplicate-start and retained faults still matter.
Product producer readiness excludes consumer VALID, making the handoff check
irrelevant to that producer-final edge. Handoff checks remain live during ACK.
The complete controller must still execute these invariants in the actual-core
test. The local bench manually assigns `forward_committed` after naturally
completing the real input checker, so it is not full-controller reachability proof.

## Parent repeat

Original process **20741 exited 0: 26 tests passed in 24.70 s**. All five reviewed
source hashes matched before and after execution. Artifacts:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-fence-parent.DYMqfY0D`.

| File | SHA-256 |
| --- | --- |
| New top | `8923b42b3574fc1418eee99c5f5819f173c73fbf7b8bb65726a7ab3a5d8a6f7c` |
| New mailbox | `e4f4c56ddab8f05d0f9b9da9a75f975e11cb8ad441581c904bfb094f3013982f` |
| Testbench | `56fe0f3f86c91370607a6fe51377e2ee52ebd014a9d3ea54b7b0eab797cbc9a6` |
| Python tests | `dc6cef6cb587366531319c5ee72ae4f5204ab24aeb4cad86cc6eda11e70e0f07` |
| Inverse recipe | `816cc8e19ebb16ad21f964a06173d2c829c3c8751df61fbdcc4f34465e7d72e0` |
| Parent log | `d616955badf08675ffc7dbaed2e79060e98cba914a3c640456866a7f3faf51d6` |
| Parent JUnit | `e768169d19e1fbe64fa71cb4fcf0204ae399eb0a3398f61fc8fbc72904f1f9af` |

Portable parent receipts are in adjacent `20260910-product-final-fence-parent/`.
The source inventory and log are byte-exact copies. The XML copy adds only a
trailing newline (independently compared after excluding that final byte); its
archived hash is `e2e919c74cbe3a8a4e7bc9747750ce468ce76e1383f1b089fac8c25d81980537`.

At depth 512, both disabled and enabled modes execute 89,228 public-state/RAM
checks, 15 sampled final authorizations, 512 inverse reads and 515 stalls.
They retain all 70 active-input bit checks, 71 malformed-final cases, seven
current-fault rows, four X/Z final rows and two epoch resets. Three deliberately
nonsampled private-authorization differences are permitted; public comparisons
remain unconditional. The four-word variant is deliberately too short for the
512-word guard: its final word stays poisoned/owned, not a healthy inverse pass.

Parent review found a missing sticky-only witness. The corrected bench pulses a
real duplicate after completed input, deasserts that pulse, then offers the valid
final while the real checker retains its fault. All other local veto terms are
checked clear. Removing that sticky term now fails the sampled-edge assertion,
as do six other missing-veto mutants. This isolates the local term; the full
wrapper would additionally latch its global fast fault after the duplicate.
Earlier 25-test and 85-test results are retained, not substituted for this repeat.

Additional tests reject unconditional publication, an intentionally broken
active-input caller, invalid -1/2/X/Z options and lost top-to-mailbox flag binding.
The full-top reset shadow uses a parked FFT stub: no active/paused-clock reset,
vendor arithmetic, capacity, physical CDC or board qualification is implied.

## Next gate

Authorized next: additive offline actual-core preparation and observer tests.
Preserve all old numerical vectors, status/CDC/ROM observers and acceptance
criteria. Attach the sampled-final and controller invariants to the real top,
verify complete hierarchy binding and exact source closure, and reject weakened
observers through directed mutations. Freeze and independently review preparation
before any vendor execution. No synthesis, route, receiver image or flash is
authorized by this local result. The main runtime HDL gitlink remains unchanged.

The implementation-side source/evidence is now published on the separate
ROM-prefetch DNM branch: FW `51ed772274e560ec52210df707d1db5014aa2884`,
HDL `f8c175444f29898022782175cf97647f3c7f0372`; tested sticky-witness source
is FW `61d5ff33c5faff20c4a05540e8efdb08f03c7709` / HDL
`a226dd615db76830928c83253d204deccdff41e8`. Parent read the complete result
report and verified the committed outer archive closure (three payload files,
manifest `d4789a8f56a233e6ffad03d3a15e1f97c2f0f367d09f8de5d243d16cb8fa7aed`).
That integrity check is not a new test run or independent inner-archive audit.

## Actual-controller preparation independently repeated

Parent read the complete additive preparation helper, actual observer/binding,
all new tests and the result report at FW
`e2abf283b08e73c439bade8b5df5335aeb9410f5` / HDL
`eb20e3940e69d28c7d26d05877e3006549da86c0`. Independent original **48393
exited 0: 60 tests passed in 28.28 seconds** (34 preparation/observer tests plus
the unchanged 26 local-fence tests). Five source hashes matched before/after.
Artifacts: recovery-parent `product-actual-parent.hMYnJBQr`.
Log: `190d3f8dfa26fee28b8d04e6e0578e4f920221d71ddb310a282c17de7a8f9ea6`.
JUnit: `6f548dda2bbabd5b52f9e478927c7cd954dbbfce2c9935420249d84628e3b730`.

Parent also independently checked every file in the proposed 65-file bundle,
the exact runner/helper identities and the frozen helper's own admission from
the prepared directory. Preparation is
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-actual-prepared-v1`:

- Inventory: `7adf2efa0a242b89ccfbb387b00210e76841ba544cbae4cef97efc861acf59b2`.
- Runner: `2d3b5008f0d087614000ae518421cd9d800aadeb98a747f47fce01d8e76cc6e3`.
- Helper: `39141329e600b15c2ff9357d952d3cd148d6db3126fff2c394108073db49b853`.
- Observer: `632273d1d31829964a2197d1cb967dbceb9ee72ac77cda213c172fb7d9ba1087`.
- Binding: `4b04032bb8eda1d597cc03b972c02839880caf4b28bf70de2176dda43fca3211`.

The whole bench and runner invert to the accepted K1/M1 preparation. All old
vectors, references and observers remain literal. The old 217-field inventory
compares 216 fields unconditionally, including all 18 internal product-bank and
nine wrapper fields. Only core status payload may differ when both status-valid
bits are exactly zero; there is no product-bank or inactive guard-data exception.
Old stimulus forces public ready/valid aliases, so an extra input-only mailbox
shadow would not share its environment. Instead, the unchanged independently
driven complete reference retains those comparisons. The additive observer
checks actual sampled authorization and predicts the old request transition;
it does not drive or mask the DUT. The standalone four-state observer fixture
checks 1,024 branch tuples, not real-controller reachability.

Complete parent test receipts are archived in adjacent
`20260910-product-final-parent-preparation.tgz`: 5,487,690 bytes, SHA-256
`53e86f079cf1f4457b1717689fefd0290fa3735746c8c7faa626b28bc720c1cb`.
Contents compare back to the original tree; redundant pytest `*current` aliases
are omitted. Original files remain intact.

No vendor execution is implied by this repeat. A unique runner owner, exact
external source pins, pre/post source/IP checks, preserved failure exits and an
independent observer-scheduling review are the remaining launch gate. No retry,
physical run, receiver image or radio operation follows automatically.

### Source-specific execution approval (14:49 UTC)

The independent sampling/force-seam review found no concrete counterexample in
the frozen stimulus: observer `632273d1`, binding `4b04032b`, actual bench
`68aab9352336490972dba7b05b59c9fcd6c3a813f741af8ee4590f25aec7870b`, extras
`0fe41dfe61e375e9cc4dadc9d1eff4179ba34fe1c068a49cb2e28d20079cb9b3`.
Sampled authorization remains unconditional before phase/ownership assertions.
The inherited public-valid force occurs in the drained missing-status epoch;
ready forces only drive low. No frozen same-edge writer was found that invalidates
the observer's pre-NBA prediction and post-NBA request-toggle comparison. This
review does not cover arbitrary future posedge stimulus.

Parent completely read and independently checked the unique owner:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-actual-owner-v1/owner.sh`,
SHA-256 `62e4fa75b645f200b9c6bbccc0a43cf6e7cda0c2f58d04245128f5da9b24cb68`.
Its literal inverse restores the old successful owner with eight declared
replacements and an added three-line exact before/after pin check. Bash syntax
passes; launch/project/start/receipt targets were absent and non-symlink, TMPDIR
was writable and about 47 GiB was available on the non-/tmp filesystem.

One actual functional vendor run is approved for that owner and the exact
65-file `7adf2efa` preparation, R/D/S/C/K/M/P=1111111, extras=1, 175 MHz,
QUICK_MUTATION=0. The implementation agent owns its original process through
terminal completion. No retry, source edit, synthesis, routing or radio action
is authorized. The owner preserves tool failure plus post-source/IP/receipt
audits, and success still requires all four unchanged complete numerical CSVs
and every old/new terminal gate. Approval is not a passing result.

The reviewed preparation/evidence is pushed to the separate DNM remotes at FW
`b187e467e948362500e531935f9fd92756aa1b22` / HDL
`420606aa1cd7e7691332387782a894fc88cda7d7`. Parent verified its seven-member
committed outer closure, manifest
`f3d5631fb84b00289a969de32bc3396df0882288537615e90f6d52a742be043e`.
This is archive integrity, not an independent inner-tar or new behavioral pass.

## Completed actual run and independent parent audit (after 14:59 UTC)

Original owner50316 exited0, 14:49:52.450519799 to14:59:41.029770790 UTC;
vendor wall time588.57 seconds. Process, after-integrity, IP audit and result
receipt exit files each contain exactly `0\n`. No retry occurred.

Parent audit original69441 exited0 at recovery
`product-actual-verify-parent.ybhwMNFo`. It independently rechecks the externally
pinned owner/helper/runner/65-file manifest, every frozen source, matching
before/after snapshots, all19 generated `.xci`/`.vhd` files with exact inventory,
the frozen composed result verifier and the unique original terminal marker.
Generated-IP checks are after-run identity, not precompile equivalence.

All four complete CSVs retain the historical hashes above: main candidate and
reference each589950 lines/35655334 bytes, extra pair each33180/2055036.
The existing ROM, fault-CDC, exact-control and extra-epoch gates all pass.
The new producer-final observer records pre/post623129, sampled140,
authorized140, closed140, nonsampled-private3, inverse-owned38950,
owned-stalls5458, current-fault7882, resets4011 and private-reset164648.
Public-overlap63 is observed, not used to mask a comparison.

Sampled veto/unknown/malformed counts are explicitly zero: this actual run
does not replace the directed local-fence fault witnesses. Qualified core status
records1246258 samples =953795 raw-equal +292463 invalid-only differences;
this is NOT a raw217-field equivalence claim. The216 other fields remain
unconditional, including product ownership and payload fields.

Parent audit source and JSON are archived as
`20260910-product-actual-parent-audit.tgz`,2510 bytes, SHA-256
`5c0dc865c522f7a7c832631590907a5e7cf8d4585d50d8a88cf1da87138be552`;
`tar --compare` matches retained originals. The implementation owner separately
archives the complete vendor evidence, not merely this compact audit.

This qualifies source-specific OFFLINE physical preparation for the same
product runtime8923b42b/e4f4c56d, preserving the ROM baseline and constraints.
No synthesis/routing launch, receiver promotion, timing pass or radio operation
follows automatically. Physical timing remains the deployment blocker.

### Portable full actual evidence

Parent independently verified the exact committed archive at HDL
`734578cef0ce51ba5a280ceee91b72c6878e4dca`, FW report/gitlink
`56e104530a9d08c1913ed055d9845e731f8535ad`:
`library/starlink_pss_acquisition/evidence/producer-final-actual-v1`.
Manifest `95e977b196d7c38bea2a68ceec12107e2212e5ae78e399ba8627804959c5f8d1`
closes138 payloads/139 tracked files, all hashes checked directly from Git.
The first packaging commit omitted nested `prepared/SHA256SUMS` due to a broad
basename filter; the owner caught and added it before publication. No actual
source or result changed. This archive integrity check is separate from the
parent's earlier complete functional/source audit.

The archive retains full CSVs, source closure, logs, generated IP and lossless
WDB gzip parts (each at most40MiB). Original WDB128374373 bytes has SHA-256
`00ef393f8a66be5777d9996e5171f5fcebe1804c49c8efe8abf3bdae26eb667f`.
The owner executed exact reconstruction; parent checked committed part hashes,
not an additional WDB reconstruction.

Physical derivation must retain the canonical source/output mailbox AND add
the product-fence mailbox: eight runtime Verilog files, not the old seven.
Rename only the top, explicitly bind P1, and use the new `fence-preparation.json`
settings; the inherited `preparation.json` intentionally describes the old base.

## Physical preparation repeated; one synthesis approved

Parent original10408 exited0: **33 passed in63.32 seconds**, at tested FW
`3bdaaf06440f969520acaa8828b6c39bc60dc820` / HDL
`6923f5352951f8e03b9c29b6d4ef3c091a3cac90`.
Recovery `product-physical-tests-parent.hdSEEaNh`; generator/test before/after
identities remain exact. Parent read the complete generator/tests, unchanged
synthesis owner and whole114-line generated Tcl, including its literal inverse
to the old ROM runner. The separate parent offline smoke1136 also exited0 at
`product-physical-smoke-parent.3qV9fpx4`.

The owner's frozen `product-final-physical-prepared-v1` matches parent smoke:
19-file inventory `b3c446578c0c35f8e0f199aa12f66d8635b6f7d21c9b97713a5ffed2ac2b0f06`,
generated helper `d22bda330f571774a3099d0da9615a6a445e58fb4aecf43d10e6657fc954e876`,
runner `d46e1f2f1def64f6021c652b65b792ecfc554116b791ef99bec525380ea86406`,
unchanged owner `d0f36ce2817ab20baaff8668b6743e367d296f7a60e714099fe69aa5b6912111`.
Parent verifies all19 source hashes; clocks, part, strategy and constraints are
unchanged. Incorrect/missing/duplicate/X settings, rewritten source inventories,
old-only actual evidence and damaged owner/terminal receipts are rejected by
the offline suite. No vendor project is created in those tests.

One exact-source OOC synthesis is approved using that unchanged owner, the
external inventory above and NEW recovery target `product-final-synthesis-v1`.
The implementation agent owns the original process to terminal, preserves all
source/IP/resource evidence and may not retry or route automatically. This is
not a timing, full-receiver or radio approval. The target was checked absent
and non-symlink; no prior build is overwritten.

Parent33-test log SHA-256
`44b148ad2f7f8b85e4290826b5e4cfe46d381dd9bcaf585305b954cc59625e09`;
JUnit `3b4398a7dab472e080a60afd2c708d49af089b677f682bd614f145a29d18c379`.
Both parent smoke and full-test trees are preserved in
`20260910-product-physical-parent.tgz`,13195187 bytes, SHA-256
`3db77b435be7294f60a2f0754826c9695b35d6b95a7a21d5a489fc9d5dc411d9`.
Archive compares to retained originals; redundant pytest `*current` aliases
are omitted, not followed or deleted.

## Synthesis passed; exact diagnostic route approved

Original75133 exited0 after127.892438 seconds, started15:22:18.723278 and
ended15:24:26.615810 UTC. Before/tool/after/return statuses are all0, all eight
products nonempty, zero black boxes. Mapped2064 LUTs,4607 FFs,21 DSPs and
15 RAMB18s: +5 LUTs versus ROM synthesis, unchanged FF/DSP/RAM. This is not
routed utilization or a timing improvement. CDC remains17 informational and
139 warning paths;114 input/124 output delay omissions remain unqualified.

Parent20406 independently exits0, recovery `product-synth-audit-parent.3ab5RYuC`.
It rechecks the external19-file inventory/helper/owner pins, full copied
13-file source closure, all eight product sizes/hashes, composed source
admission, owner completion, all recorded source/IP hashes and seven exact
enabled generics. The reports name `starlink_pss_fft_bank_owned_product_fence`
and device `xc7z010clg400-1`. Clocks remain source100MHz/island175MHz
(5.714ns constraint); the original generated-IP factory is unchanged.

Accepted synthesis DCP2171713 bytes, SHA-256
`41c756bdc45635b1107d73ad741826e5a8f8fa276dc159468ec2355c16203aa6`.
Root and independent reviewer read the entire old route owner and unchanged Tcl.
The new owner at recovery `product-final-route-v1/own_route.py`, SHA-256
`5938ff6c7141676e3629547196e1d5aec57f5bd77c8df2fbe76edbc01e6873de`,
strictly restores old owner `e9b7ca139...` with exactly three substitutions:
new synthesized DCP path, new prepared Tcl path, new accepted DCP hash.
No other owner/constraint/strategy change. Root checks all route/tmp/log/receipt
targets absent and syntax valid before launch. Tcl remains
`0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.

ONE diagnostic route is approved for that exact owner/DCP/Tcl. The implementation
agent owns its original process to terminal; no retries or radio operations.
The route Tcl alone does not prove P1/top/device provenance: that binding comes
from the accepted synthesis audit above. A successful owner exit only proves
a complete diagnostic record; setup/hold, route completeness and crossings must
still be examined. No full-receiver, I/O or deployment qualification is implied.

Parent read-only synthesis audit script and result are archived as
`20260910-product-synth-parent-audit.tgz`,2321 bytes, SHA-256
`6d41bf6f6cf70d3ff9bf1a2645a33a93fa826f18f7ff81b9f854284ea6881c6f`.
The archive compares to its originals. This compact audit is separate from the
owner's full source/DCP/report archive.

### Published synthesis/preparation closure and routed outcome

Parent independently verifies committed synthesis archive77 payloads/78 tracked
files at HDL `57322987e9e188dcd20a6cc2cac0a3f6b6404a93`, manifest
`274168fd85afb13f9ebf800daffb0e59652c40ee258411cf377d0e5ccdf2c010`.
Preparation archive outer closure verifies4 payloads/5 tracked files at HDL
`fc37b96b8bffba00104d2f24ff3cfb17acd96981`, manifest
`2cac021ac69f2de5ec82d9ff659896d97787e8f355632d570f218309ef6fedf6`.
The owner separately verified its504 inner payloads; parent does not relabel
that as an independent inner audit.

The approved route63593 subsequently completed but FAILS timing, -1.492ns.
No promotion: see [complete failed-route record](20260910-product-final-route.md).
