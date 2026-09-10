# Committed evidence publication check

The local archive checks had missed a publication defect: Git ignore rules
omitted logs/reports/checkpoints from four manifest-based control archives.
The original files remained intact. An additive repair committed exactly the
missing manifest members; it did not change RTL, tests, results or manifests.

`tools/verify_starlink_git_evidence.py` now makes this check repeatable. It reads
only the requested complete commit ID's Git objects, requires the externally
reviewed manifest SHA256, requires the exact committed path set, rejects links
and noncanonical/duplicate/self-referential paths, and streams each blob through
SHA256. Local ignored, untracked or staged bytes cannot satisfy the check.
It neither writes files nor performs network operations. A successful result
proves committed archive integrity, **not** test validity, remote availability,
timing closure or deployment suitability.

Example for the repaired route archive:

```sh
python3 -B tools/verify_starlink_git_evidence.py \
  --repo /tmp/starlink-coarse-alternatives.Y3JzOI/completed-input-fence/hdl \
  --commit ae7c0ec29812efb2c0d442cbe9dfb6b3b0eaab24 \
  --archive library/starlink_pss_acquisition/evidence/exact-control-combined-route-v1 \
  --expected-manifest a870afb08a029cc48b0f13828a7577d048de844bf6aeccab4a9624461a8c430b
```

Thirty offline tests exercise ignored-but-present evidence, additive repair,
old-pin rejection after repair, independence from working-tree/index mutations,
committed corruption/extra files/symlinks/missing manifests, unsafe paths,
malformed manifests, moving refs and the command-line interface. Initial run:
30 PASS / 0.20s at `/tmp/starlink-git-evidence-tests.2Hn1mU`. An initial lint
failure for a non-executable shebang was corrected by removing that shebang;
the supported invocation is through Python. Lint now passes.
Final unchanged-behavior replay:30 PASS /0.23s at
`/tmp/starlink-git-evidence-final.Q0wsRK`, with lint/diff checks passing.

The checker also passed all five actual repaired archives at HDL `ae7c0ec2`:
306 CDC,37 route,43 synthesis,129 physical-preparation and83 actual-run members
(598 members plus five manifests). It rejected the original route commit
`2ccfac2e` because committed artifacts were missing. These checks use real Git
objects, not an invented mock of the historical failure. The original actual-run
83-member archive was already complete and did not need repair. Remote push
receipts remain separate evidence in the parent review journal.
