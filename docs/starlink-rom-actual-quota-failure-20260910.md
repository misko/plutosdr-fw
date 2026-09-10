# ROM actual evaluation: retained quota failure and relocation proposal

The single authorized K1/M1 evaluation **did not complete**. Original handle
23845 returned1 after a waveform write hit `/tmp` user quota at epoch160.
This is not a passing actual test, a ROM semantic counterexample, a raw217
pass, or physical evidence. No retry, runtime edit, gate relaxation or radio
action occurred. Offline 147-test evidence remains at FW314d1381d / HDL54af5727.

## Original failure and new read-only observations

Source authorization was FW `e7d8b229e1719eb4fd40810b4e5be5fad98a96d6`,
HDL `54af5727801b3f0cb3a9a178b3135cc6e5a311fd`, R/D/S/C/K/M111111,
extras1,175 MHz,QUICK0. Source inventory remains
`6f5eddb99510e869bbe65548acc6ed64cd76bd98908aacfcd6e1c0361ccbe4ae`.
The exact last line of the original launch log is:

```text
WDB FATAL ERROR: failed to add file block (WdbFileBlockManager) for the following reason: Disk quota exceeded
```

The original owner tool response reported
`process=1 after_integrity=0 IP_audit=0 independent_receipts=120`.
However its process/time/end/post-source/IP/receipt files are zero bytes because
their writes also hit quota. The original stored before/after hash comparison
therefore **fails**. Those empty files remain untouched; numeric shell statuses
do not establish that their receipts persisted. Original start was
12:25:25.886262245 UTC; launch-log mtime is12:35:45.585993140 UTC, and the
terminal was observed12:35:52 UTC. A valid `/usr/bin/time` terminal wall-time
receipt is unavailable. The simulator log is buffered/truncated earlier than
the launch log and does not itself contain the final waveform error.

Fresh, explicitly separate read-only checks verify all56 inventoried files,
the exact manifest and runner hash; fresh hashes equal original before.sha256.
Frozen `verify_prepared` still accepts all exact settings/source bindings.
Frozen `verify_result` rejects `failed or incomplete actual run`. Neither new
observation repairs or relabels an original receipt.

Both partial main CSVs are34373632 bytes and569129 newline characters, SHA
`5963a605e4da325207d6672939b38b0c9b49a28fbd70f82652adcbb85a9735a2`.
They match each other and byte-exact prefixes of the passing C1 CSVs, but end
mid-line at cycle569128/epoch160. The extra CSVs were never created. All292463
invalid-status-only log rows are retained, each with both valid bits zero;
there is no complete exact-control, ROM or qualified-status terminal receipt.
Partial equality is not a completed numerical, fault, reset or ROM-coverage
qualification.

Warnings retained from the original launch log: one IP-name-length warning,
one empty compiled-library path, eight forward-declared identifiers, sixteen
initialized non-net outputs, one glbl top-parameter warning and one existing
distributed-cause pretty-print warning. Generated IP was absent before project
creation; a fresh after-failure inventory hashes all19 generated .xci/.vhd
files. This is not a before/after generated-IP equivalence or synthesis claim.

The failing mount was `/tmp` tmpfs with `usrquota`; aggregate free space and
inodes remained available. The `quota` utility was absent. Parent recovered
space by moving only its own three terminal pytest trees, outside this task;
this task deleted or relocated none of the original failure evidence.

## Lossless portable package

Original run and owner remain under `/tmp/starlink-rom-prefetch.j829ht/`.
Packaging and temporary data are under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-failure-23845.OlNSaRYK`.
The portable directory is copied to HDL
`library/starlink_pss_acquisition/evidence/rom-read-ahead-actual-quota-failure-v1`.
It includes the complete freeze, original owner/empty receipts, lossless full
logs and partial CSVs, generated IP, fresh audits and the explicitly labeled
original tool-response transcription. A separate relocated-owner proposal is
marked offline and is not a second run receipt.

The original partial WDB is119349248 bytes, SHA
`e50d813dd2ecb344f013bbb469c8f63047dec90a669903a582e856666d826e57`.
Its gzip is108587229 bytes, SHA
`723fdc2da9f2c330b3b6d4ff71ce38d1c6a70a0158b7dec85c9a39d3192b7831`.
Three parts are each at most40MiB; the unchanged previously tested helper
reconstructed and verified both exact identities in a fresh non-/tmp directory.
That proves byte preservation, not a healthy or readable complete waveform.
The monolithic gzip stays outside the worktree; originals remain intact.
Archive HDL commit is `04a2680b90a68efd53ab932748a54f401939eef0`;
126-member manifest SHA256 is
`a12ac3ce04e0644cfe2a5460354091992500ddcc0e68106b3f01d75021ac6786`.
The read-only Git-object gate passes all126 members with exactly127 tracked
files; receipt is `git-object-verification.json` under the non-/tmp packaging
directory above. The portable payload totals131579949 bytes and no member
exceeds41943040 bytes. Actual WDB reconstruction and all compressed raw-file
identity checks also pass; no original artifact changed during packaging.

## Proposed successor: path-only, not launched

Prepared copy:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-relocated-actual-v2.CWJkzwEi/rom-actual-prepared-v1`.
All56 members plus the inventory are byte-identical to the original freeze;
no project, launch log or journal exists. The frozen helper, invoked from `/`,
accepts the relocated path with the same R/D/S/C/K/M111111 settings. Runner
SHA remains `9f198abf60d9119eae2ef565ae3d65b64104f93ce5f1b5be4b2e89776dd3deed`.

The proposed owner differs from the original only in five absolute base-path
substitutions; reversing those five restores the entire old script literally.
`bash -n` passes. Owner SHA is
`4c5db6e2acade10b16ccf71ec1e458bad61b63a4ddf5f9055519d57edd420631`.
Proposed invocation, requiring separate parent authorization:

```sh
TMPDIR=/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-relocated-actual-v2.CWJkzwEi/tmp \
bash /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-relocated-actual-v2.CWJkzwEi/rom-actual-owner-v1/owner.sh
```

The owner retains explicit SuSE Vivado2022.2/two-thread invocation, original
source/CSV/receipt gates and no-overwrite behavior. All owner/project/temp
paths are on the recovered disk; no source or Tcl directive changes. After any
future terminal, independent checks must again require exact manifest and
stored before/after equality, nonempty persisted receipts and all original
numerical/fault/ROM/qualified-status gates. A failure cannot be inferred away
from process status. No successor actual, synthesis or route is authorized by
this relocation preparation.
