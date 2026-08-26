# Tandem AGC firmware development, release, and hardening plan

Status: working release plan

Snapshot: 2026-08-26

Target release: `v0.41-plutoplus-spf-tandem-agc-v8`

This document turns the current tandem AGC implementation into an executable
development, refactoring, test, deployment, verification, and release plan. It
supplements [TANDEM_AGC_V2_DESIGN.md](TANDEM_AGC_V2_DESIGN.md),
[RELEASING.md](RELEASING.md), [flashing.md](flashing.md), and
[tests/radio_hardware/README.md](tests/radio_hardware/README.md). If a command or
release rule conflicts with `RELEASING.md`, stop and reconcile the documents
before touching hardware or publishing an artifact.

## 1. Executive decision

Work proceeds on two deliberately separate tracks.

### Track A: close the tandem AGC v8 release

RC5, RC6, and RC7 are immutable failed/rejected attempts; RC8 and RC9 are
immutable successful indexed builds that never crossed the hardware transition
boundary. None is a
branch to repair in place. Their exact build branches, manifests, source locks,
runs, artifacts, and indexes remain unchanged for reproducibility. RC6 is locked at
`fb1cb04085fda4854f964481d5d5427b6934d58b`; trusted run `32944830787`
completed a fully routed, timing-clean implementation but failed the stale
post-route validator before packaging. RC7 trusted run `32948720383` then
completed the full build and integrated route and produced bundle SHA-256
`7f13d6dd3f814af1a1e0d06d65535d2f60499b4bb3c0ab0e5cc4e7b8c8836f34`,
but review rejected it before evidence assembly or hardware because member and
checksum order depended on locale and shell-array order. There was no
deployment. Its branch `codex/firmware-tandem-agc-v8-rc7` and source lock
`refs/tags/tandem-agc-v8-rc7-source/firmware-v1` remain immutable reproduction
history. RC8 trusted run `32952343526` then built exact commit
`cc62b65ea8082aad0625a891f0b79b81c78e78c7`, passed integrated validation,
produced deterministic bundle SHA-256
`d55b58e489a58c3c8868f4bfcec4a7901c229a25e801c172bf2dd1fa08965c77`
and DFU SHA-256
`2c74f06bff072d9c3250e5e028e18ddda4f700f5960cd07153432f1a081a8f49`,
and produced verified candidate-index SHA-256
`d94b9c37a8c6f1e5935df5ae4bdfd03be49b7aba40236a32386382a0f09004a8`.
It performed zero hardware deployment because the deployer required a separate
historical transition-proof input in addition to its live safeguards.
RC9 then removed that redundant input. Trusted run `32957388515`, attempt 1,
built exact commit `9f47ef1746eaf356e53fe52cd9eb608ee8421c62`, passed the
integrated route, and produced bundle SHA-256
`5f3eb4a772fb808f4598c4cc11d6a10936fecdaf045636d33ddfeaeaa9927dc7`,
DFU SHA-256
`407c560be90cfdbf459b92f1f76352f83f09cabf9c5f336375bd85868454975f`,
FIT SHA-256
`19e85e9b1c6ca12e41f8566fcff609a781aedfc9f0135b7c042aa25872a60115`,
and verified candidate-index SHA-256
`d2784863cfb74c34e98a2295a1b7532fc19f7f93ef90045b726055f1f99d3efd`.
Its first live execute stopped during the initial SSH read, before reboot, DFU,
or receipt: competing connected `/24` routes selected the wrong serial, and a
temporary exact `/32` route then exposed the factory image's password-only SSH
service. The route was removed; no radio changed state and RC9 had zero
deployments. Its branch `codex/firmware-tandem-agc-v8-rc9`, source lock
`refs/tags/tandem-agc-v8-rc9-source/firmware-v1`, trusted run, artifact, and
candidate index remain immutable reproduction history. The active candidate is
RC10.

RC6 introduced one deliberately narrow, behavior-preserving fit refactor. The
mapping replaces three mutually exclusive dwell counters with one
eight-bit saturating counter plus a two-bit qualification-class tag. It also
replaces the two stale-latch episode booleans with one two-bit binary episode
token, removes the redundant eight-bit `event_index` shadow, and applies
`use_dsp = "yes"` only to the wide `pwr_div` and `evt_seq` accumulators. The
dwell tag is part of the safety property: a class transition must start fresh
qualification and can never inherit dwell credit from another class. Apart
from that resource-recovery change and its tests/lineage, freeze functional
RTL, kernel, libiio, ABI, constraints, and RF-test behavior. RC7 retained those
exact RTL semantics and corrected the integrated validation route. RC8 retained
that behavior and corrected deterministic bytewise bundle/checksum ordering.
RC9 retained that firmware/package behavior and removed the redundant
historical-proof input. RC10 retains RC9's firmware behavior and deterministic
package implementation; only exact temporary `/32` host-route isolation,
private password-file SSH transport, measured receipt v3, and forward-only
release identity change.
Do **not** expand this exception into an architectural controller rewrite
before v8.

### Track B: simplify and harden after v8

After v8 is published and its exact behavior is preserved as a reference,
refactor the controller and verification tooling in small, independently
reviewable slices. Each slice must preserve the public ABI and pass lockstep,
simulation, formal, routed, and—where the affected boundary warrants it—hardware
checks.

This separation is the main schedule-control mechanism: release closure is not
held hostage by cleanup, and cleanup is not rushed under a release deadline.

## 2. Current state

### 2.1 What is working

- `tandem-agc-v7` remains the current hardware-qualified release.
- The tandem v8 implementation has a versioned session lifecycle, paired gain
  control, event FIFO, strict metadata parsing, guarded hardware campaigns, and
  fail-closed cleanup.
- The Icarus suite covers CDC primitives, the AD9361 model, two clock ratios,
  randomized lifecycle stress, and the AXI surface through
  `hdl-tandem/run_tests.sh`.
- Kernel acquisition-order and stale-detector clearing guards exist in
  `scripts/test_tandem_acquire_sequence.sh` and
  `scripts/test_tandem_detector_latch_clear.sh`.
- The offline Python suite has planted failures for metadata, lifecycle,
  continuity, signal quality, transient analysis, campaign resumption, cleanup,
  and evidence validation.
- All current HDL benches pass at both supported clock ratios, including the
  direct increase/conflict/re-arm class-transition cases that prevent shared
  dwell credit from crossing evidence classes.
- RC6 trusted run `32944830787`, attempt 1, built exact commit
  `fb1cb04085fda4854f964481d5d5427b6934d58b`. Vivado placed 4,399 of 4,400
  slices, used 74 of 80 DSPs, routed 32,908 of 32,908 nets, and closed timing
  at WNS `+0.645 ns`, WHS `+0.022 ns`, and minimum bus skew `+8.606 ns`.
- That RC6 run failed only after implementation because its committed
  validator expected stale report-state, DSP, and CDC details. It uploaded
  diagnostics only and produced no deployment bundle, candidate index, or
  DFU. The implementation numbers de-risk RC5's capacity failure but do not
  authorize RC10 or replace its clean offline/OOC and trusted build gates.
- RC7 trusted run `32948720383`, attempt 1, completed its full firmware build,
  integrated route, and report validation and uploaded bundle SHA-256
  `7f13d6dd3f814af1a1e0d06d65535d2f60499b4bb3c0ab0e5cc4e7b8c8836f34`.
  The candidate was rejected before evidence indexing or hardware because
  archive/checksum order was locale- and shell-array-dependent. There was no
  deployment. This proved the unchanged firmware could fit and route, but not
  that the rejected package could authorize later bytes.
- RC8 trusted run `32952343526`, attempt 1, built exact commit
  `cc62b65ea8082aad0625a891f0b79b81c78e78c7`, fully routed 32,908 of 32,908
  nets, placed 4,399 of 4,400 slices, used 74 of 80 DSPs, and closed timing at
  WNS `+0.645 ns`, WHS `+0.022 ns`, and minimum bus skew `+8.606 ns`.
- That run produced deterministic bundle SHA-256
  `d55b58e489a58c3c8868f4bfcec4a7901c229a25e801c172bf2dd1fa08965c77`,
  DFU SHA-256
  `2c74f06bff072d9c3250e5e028e18ddda4f700f5960cd07153432f1a081a8f49`,
  FIT SHA-256
  `30f7816ea2f1b66aff928613b95748f952cafbb35bc7320a05bfdd5e3075b9d8`,
  and verified candidate-index SHA-256
  `d94b9c37a8c6f1e5935df5ae4bdfd03be49b7aba40236a32386382a0f09004a8`.
  Integrated validation passed and `firmware_release_eligible` was true.
- RC8 stopped before touching a radio because its deployer required a separate
  historical transition-proof input in addition to the live exact-command,
  identity, QSPI, and safe-state checks. It performed zero hardware deployment.
  RC9 kept the firmware and deterministic package implementation unchanged
  while removing that redundant input and versioning the measured receipt.
- RC9 trusted run `32957388515`, attempt 1, built exact commit
  `9f47ef1746eaf356e53fe52cd9eb608ee8421c62`, fully routed 32,908 of
  32,908 nets, and closed timing at WNS `+0.645 ns`, WHS `+0.022 ns`, and
  minimum bus skew `+8.606 ns`. Its bundle, DFU, FIT, and verified candidate
  index have the exact hashes recorded in section 1.
- RC9's first execute attempt stopped at its initial SSH read. Four radios use
  the same `192.168.2.1`, and interface binding did not override their
  competing connected `/24` routes; strict known-hosts verification rejected
  the wrong serial. A temporary exact `/32` route selected the intended radio,
  after which the former key-only transport could not authenticate to the
  factory password-only image. Cleanup removed the route. No reboot, DFU,
  detach, receipt, or radio state change occurred.
- The RC10 guarded deployer now refuses a pre-existing exact route, obtains and
  verifies a temporary `192.168.2.1/32` lease through the selected interface,
  uses a private mode-0600 password file through `sshpass`, revalidates the
  credential and route for every SSH call, and verifies route deletion before
  publishing a v3 receipt. Password bytes are never printed, hashed, or
  archived.
- The full hardware-free release gate on RC5 commit
  `af2e1821436996188fd32cc1cf8a0f8a41f31fc1` passed with 1,093 tests and five
  explicitly deselected hardware tests. The same exact commit's routed OOC
  result passed with WNS `+3.765 ns`, WHS `+0.079 ns`, and zero failing
  endpoints. Its scope is intentionally limited:
  `firmware_release_eligible=false` and
  `integrated_route_required=true`.
- Earlier hardware work proved the test fixture and broad quality approach on
  four radios. That evidence is valuable harness validation, but it does not
  qualify the post-RC4 RTL.

### 2.2 Why RC4 through RC9 cannot be promoted

RC4's protected firmware source lock is
`557a08749d9c0c34fe8096099b5be9d2b2a1b24f`. Stale-small-ADC-latch recovery was
added after that lock. The change affects top-level RTL policy and pulse
behavior, so the following evidence does not transfer to the current branch:

- the RC4 protected firmware lock;
- the RC4 integrated bitstream and timing/CDC results;
- the RC4 packaged DFU and attestation; and
- the RC4 RAM-boot and hardware campaign reports.

RC5 therefore needed a new immutable source lock, integrated route, artifact,
and full four-radio qualification. The RC4 lock and tag remained unchanged.

RC5 commit `af2e1821436996188fd32cc1cf8a0f8a41f31fc1` was then locked and
dispatched through trusted Actions run `32933327011`, attempt 1, with exact
identity `v0.41-plutoplus-spf-tandem-agc-v8-rc5`. Identity, reset, source, and
offline gates passed, but integrated Vivado placement failed before artifact
upload. The Zynq-7010 has 4,400 slices; fixed and macro placement left 2,340
available while 2,357 instances still required placement, a 17-slice deficit.
No RC5 DFU or deployment bundle exists. RC4 had placed at 4,399 of 4,400
slices, so this is a real capacity limit rather than a transient CI failure.

RC6 then locked the class-tagged shared-dwell implementation at
`fb1cb04085fda4854f964481d5d5427b6934d58b` and dispatched trusted Actions run
`32944830787`, attempt 1. The full design fitted and routed cleanly: 4,399 of
4,400 slices, 74 of 80 DSPs, 32,908 of 32,908 routed nets, WNS `+0.645 ns`,
WHS `+0.022 ns`, and minimum bus skew `+8.606 ns`. Its post-route validator
rejected stale report-state, DSP, and CDC policy assumptions, so the run
uploaded diagnostics only. No deployment bundle, candidate index, or DFU was
produced or deployed.

RC7 then used the corrected validator without changing firmware behavior.
Trusted Actions run `32948720383`, attempt 1, built and routed successfully and
uploaded a bundle with SHA-256
`7f13d6dd3f814af1a1e0d06d65535d2f60499b4bb3c0ab0e5cc4e7b8c8836f34`.
Review rejected it before evidence assembly because its bundle/checksum member
order depended on locale and shell-array discovery order. No deployment or
hardware use occurred.

RC8 then made the package/checksum ordering deterministic without changing
firmware behavior. Trusted Actions run `32952343526`, attempt 1, succeeded and
its verified candidate index has SHA-256
`d94b9c37a8c6f1e5935df5ae4bdfd03be49b7aba40236a32386382a0f09004a8`.
No radio was touched: the RAM deployer still required a separate historical
transition-proof input even though execution already measures the properties
that matter. RC8 therefore cannot be promoted after its source lock.

RC9 then completed the full hardware-free path and candidate indexing but its
first live execute exposed the duplicate-IP route and factory-password
transport gaps before any hardware transition. Its branch, source lock, run,
artifact, and candidate index are burned and must never move.

The RC5 through RC9 build branches and source tags are immutable. RC10 is a new
source identity retaining RC9's firmware implementation, integrated validation
policy, and deterministic packaging. Only the host route/authentication
boundary, receipt v3, and lineage change. RC10 has a new manifest, exact
branch, source lock, trusted build, evidence archive, and hardware campaign.

### 2.3 What has been causing trouble

Most failures have occurred at boundaries rather than in the basic gain truth
table:

- synchronous session close versus undrained FPGA events;
- host request/response cadence versus full-frame metadata transport;
- a registered policy request versus the pulse engine at zero cooldown;
- current low-power evidence versus a latched historical small-ADC overload;
- asynchronous AXI/RX crossings, reset release, and constraint precedence;
- source locks, stamped `device-fw`, build artifacts, and hardware reports not
  all referring to the same bytes; and
- cleanup paths that must remain correct after exceptions, process death, or
  partial evidence; and
- a redundant historical transition-proof gate layered on top of live
  exact-command, identity, QSPI-integrity, and safe-state checks; and
- multiple identical device IPs interacting with connected `/24` routes, plus
  a factory password-only SSH service interacting with a key-only executor.

The implementation also carries avoidable reasoning cost:

- `tandem_agc_core.v` combines detector conditioning, dwell accounting, policy,
  stale-latch episode state, pulse requests, index mutation, event creation,
  cooldown, diagnostics, faults, and lifecycle.
- The decision-to-pulse transaction is implicit across several sequential
  blocks. The zero-cooldown bug was a symptom of this boundary.
- Stale-latch state is encoded by interacting booleans and counters, including
  combinations that are invalid by intent but not impossible by type.
- The 140-bit configuration bundle and 30-bit status bundle in
  `tandem_agc_axi.v` are manually packed. A source comment records an earlier
  real offset error after one field width changed.
- RTL tests inspect internal register names, so a structural refactor would
  otherwise require rewriting the tests at the same time as the design.
- The routed OOC launcher/validator/test stack is larger than the controller
  RTL and mixes report extraction, artifact-integrity defenses, and release
  policy.
- Several hardware modules exceed 5,000 lines and repeat acquisition and
  evidence constants across runtime code and independent validators.

### 2.4 Release blockers still open

| ID | Blocker | Exit condition |
|---|---|---|
| A-01 | RC10 source and lineage are not frozen | Shared tagged-dwell behavior, proof-free measured receipt, and deterministic bytewise packaging tests pass; all intended changes are reviewed, committed, and clean |
| A-02 | RC10 has no protected firmware source lock | Exact clean RC10 commit passes full offline and routed OOC gates; new branch and `refs/tags/tandem-agc-v8-rc10-source/firmware-v1` are pushed without changing RC5 through RC9 |
| A-03 | RC10 has no integrated artifact | Trusted RC10 build fully places/routes, passes integrated report and deterministic-package policy, and uploads the exact deployment bundle |
| A-04 | RC10 exact bytes have not run on hardware | Exact-serial RAM receipts plus full, lifecycle, transient/modulated, and soak reports pass on all four required radios |
| A-05 | Final identity and publication are incomplete | Main build is confirmed, annotated tag and immutable manifest exist, and the exact published asset verifies |

## 3. Non-negotiable engineering rules

1. A verdict is always scoped. Use `offline_pass`,
   `ooc_pass_nonauthorizing`, `integrated_route_pass`, `ram_booted`, and
   `hardware_qualified`; avoid an unqualified `PASS`.
2. Any functional RTL, kernel, libiio, ABI, constraints, or qualification-harness
   change after a candidate lock creates a new candidate and invalidates the
   affected downstream evidence.
3. Every build and test claim binds to a full commit, source manifest, tool
   versions, artifact hashes, CI run/attempt, and—where applicable—radio serial.
4. OOC implementation is necessary fit/timing/CDC evidence but never substitutes
   for the fully integrated Pluto implementation.
5. Candidate firmware is RAM-only. Do not write a candidate to QSPI.
6. Hardware qualification and deployment remain separate operations. The
   release runner deliberately never deploys, reboots, or flashes.
7. Never select a radio using only a changing USB coordinate or an ambiguous
   VID/PID. Resolve from the exact immutable serial and attest the opened device.
8. Never rebuild between hardware qualification and publication.
9. Never move a failed source lock, candidate tag, release tag, or immutable
   manifest. Advance to a new name.
10. Every handled hardware exit—success, failure, or caught exception—must prove
    TX muted, DDS disabled, selectors at ZERO, tandem released/IDLE, and no
    unexplained FIFO/fault state. An uncatchable interruption such as `SIGKILL`,
    host loss, cable loss, or power loss makes the attempt nonauthorizing; a
    fresh serial-scoped recovery must re-attest mute, selectors, runtime
    identity, tandem IDLE, and FIFO/fault state before resume.
11. Do not waive warnings by prose pattern or broad category. A waiver names a
    stable rule ID, exact affected paths, rationale, owner, and expiration.
12. Public pull requests never execute on the trusted self-hosted Vivado runner
    or touch radio hardware.

## 4. Track A — close tandem AGC v8

### A0. Freeze scope and define the candidate

Deliverables:

- A short candidate change list containing only changes since RC4 that must ship
  in v8.
- A decision on every current uncommitted file: include through a reviewed
  commit, or leave it out without destructive worktree operations.
- An unused candidate identity, expected to be
  `v0.41-plutoplus-spf-tandem-agc-v8-rc10`.
- A release requirements checklist copied into the candidate issue/milestone.

Freeze the following contracts before qualification:

- `TAG2` register map and register reset behavior;
- 104-byte tandem session request and metadata/event layout;
- detector priority and stale-latch episode behavior;
- lifecycle, ownership, HOLD/AUTO, fault, and synchronous close behavior;
- supported sample rates, clock ratios, gain-table/band selection, pulse widths,
  blanking, dwell, cooldown, and FIFO capacity;
- RF fixture safety limits and the required four-radio set; and
- report schemas and acceptance thresholds.

Gate: scope and candidate identity are frozen. A final clean candidate commit is
nominated only after the A1 tooling/manifest/route changes are complete and A2
passes; all later evidence names that commit's 40-character SHA.

### A1. Close candidate-specific test and deployment gaps

This phase may change test/deployment tooling, but it must not change controller
behavior. If a test exposes a behavioral defect, restart at A0 and rerun all
evidence. RC10 may retain its unused name before any RC10 lock/artifact exists;
after either exists, advance to RC11 or another new immutable identity.

#### A1.1 Generalize muted metadata lifecycle qualification

`tests/radio_hardware/muted_metadata_batch_lifecycle.py` was originally frozen
to RC4, one exact R18 serial, one source commit, and one RAM-boot receipt. The
generalized runner now consumes an immutable, validated candidate description;
RC10 must exercise that interface with its own source/evidence manifest.

Required properties:

- exact serial, DFU/FIT hash, source lock, build run, attempt, and firmware
  identity are inputs, not ambient assumptions;
- the runner and metadata ABI files are committed and hash-bound;
- the 64-frame muted batch lifecycle remains byte-for-byte constrained;
- all four radios can run the same logic with serial-scoped output and locks;
- close, FIFO drain, fault/overflow, and final cleanup are revalidated from the
  durable report; and
- offline mutation tests reject a changed receipt, report, artifact, source
  lock, harness, serial, lifecycle phase, or cleanup record.

#### A1.2 Lock deterministic stale-small-ADC RTL qualification

The internal stale-latch FSM/re-arm/one-pulse property is qualified by the
deterministic RTL suite, not by a mandatory RF phase. Keep exact tests at both
supported clock ratios for the low-average-power plus latched-small-ADC
conflict, fresh-dwell requirement, one paired decrease and event, chatter/
blanking/cooldown/HOLD suppression, fail-closed recurrence/minimum behavior,
and re-arm only after an ordinary large-overload decrease plus fresh neutral
dwell. These tests remain release gates and must retain planted failures for an
extra clear, early re-arm, index mismatch, or missing event.

The existing hardware observer emits only `BLOCKED` v1 and may be retained or
improved as an optional diagnostic. Its output is covered as a raw archive
member when present, but it is not a candidate-qualification phase and cannot
authorize or block promotion. Release hardware instead qualifies the external
paired behavior, transient/modulated operation, lifecycle, and safety paths.

#### A1.3 Use the authoritative RAM-only deployer

Do not automate the current generic `download_and_test.sh` or `make dfu-ram`
path for a multi-radio campaign. The guarded repository tool now requires
these explicit inputs:

- exact radio serial and expected current identity;
- absolute candidate bundle/DFU path, size, and SHA-256;
- exact expected post-boot `device-fw` and packed component identities;
- expected DFU/FIT structure and allowed firmware partition only;
- exact network interface, strict serial-specific `known_hosts` file, and a
  private mode-0600 SSH password file whose contents are never recorded;
- an explicit operator confirmation tied to the serial; and
- an absent, serial-scoped receipt path.

The tool must:

1. verify the artifact and sidecars before device access;
2. resolve exactly one connected radio from its immutable serial and bind the
   pre-reboot USB topology;
3. refuse any pre-existing `192.168.2.1/32` route, add one exact temporary
   route through the selected interface/source address, and verify that route
   before every SSH operation;
4. authenticate every SSH read and reboot request through `sshpass -f` using
   the same private password file, one password prompt, and strict known-hosts
   checking; never print, hash, copy, or archive the password bytes;
5. prove the selected DFU target corresponds to that radio, refusing ambiguity;
6. use only the firmware/RAM target—never `boot.dfu`, `uboot-env.dfu`, a full
   ZIP, or a raw MTD write;
7. perform the hardware-proven download/detach sequence;
8. require re-enumeration with a new boot ID and the same serial;
9. read back the exact live serial, Pluto+ hardware model, `fw_version`, boot
   ID, QSPI identity, and TX/DDS/DAC/tandem safe state; the candidate index
   separately binds packed component, kernel, FPGA, gadget, and 2R2T evidence;
10. where the platform permits a validated read-only operation, compare the
   firmware QSPI partition digest before and after RAM boot;
11. remove and verify absence of the exact `/32` route on success and every
    handled failure before a receipt can be published;
12. atomically write a JSON receipt containing the plan, commands, timestamps,
    identities, hashes, topology, verified route release, and outcome; and
13. never claim success after a partial or ambiguous run.

The earlier `-R`/`-e` documentation contradiction is resolved in executable
policy: the guarded deployer forbids `-R`, persistent targets, and alternate
images, and permits only firmware download followed by DFU detach (`-e`). No
separate historical proof file authorizes execution. Instead, each actual
deployment must prove the candidate index, exact serial and USB topology,
pre/post Pluto+ model, new boot ID, exact firmware identity, unchanged
`qspi-linux` digest, operator confirmation, safe final state, exact temporary
host-route lease, and verified lease removal. The immutable v3 receipt records
those measured facts and the transparent `sshpass -f <path> ssh ...` command,
but never the password bytes or a digest of them.

Bind the resulting receipt and expected DFU SHA to every candidate hardware
report. An exact version string alone is insufficient because different bytes
can carry the same string.

#### A1.4 Prepare the RC10 manifest and trusted route

All repository changes needed to build the candidate must precede the clean
offline/OOC commit. Before A2:

1. add `manifests/tandem-agc-v8-rc10-source.yaml` with the reviewed external
   component pins;
2. add `codex/firmware-tandem-agc-v8-rc10` to the owner-only dispatch allowlist
   in `.github/workflows/firmware-main.yml`;
3. update all three workflow decisions together: allowed ref, source-manifest
   mapping, and package-stem mapping, with no fall-through to an unrelated
   default manifest;
4. add the RC10 manifest to source-graph CI; and
5. update `tests/test_release_oracles.py` so the full trusted-route mapping is
   enforced.

The protected RC10 firmware source lock is created later, after the exact clean
commit passes A2 and A3. Preparing the route does not authorize a build by
itself.

#### A1.5 Close integrated-build and release-verifier gaps

Any code used to accept the integrated route or bind hardware evidence must
also be committed before A2/A3. In this phase:

- make `scripts/ci/package_main_firmware.sh` fail closed on fully routed status,
  unconstrained paths, the reviewed CDC inventory, required bus-skew paths,
  DRC/methodology policy, utilization guardrails, and routed-DCP/report hashes;
- make every package inventory and checksum list use an explicit bytewise
  (`LC_ALL=C`) order over validated member names rather than filesystem,
  locale, glob, or shell-array discovery order; replay the packaging oracles
  under `C`, `C.utf8`, and an available non-C UTF-8 locale and require
  byte-identical inventories and bundles;
- introduce a versioned narrow waiver inventory keyed by stable Vivado rule IDs
  and affected paths;
- make the DFU suffix check mandatory for a release-verification environment;
- add `scripts/tandem_release_evidence.py` with deterministic `assemble` and
  `verify` subcommands. It produces and validates immutable, stage-specific
  indexes: `candidate-index.json` before hardware, `campaign-index.json` after
  RC qualification, `final-artifact-index.json` before final confirmation, and
  `final-qualification-index.json` after the required final test mode, followed
  by `published-release-index.json` after publication. Each later index binds
  the SHA-256 of the earlier index rather than rewriting it. Together they bind
  the source lock, manifest, OOC, integrated build, Actions run record and
  optional supporting attestation metadata, exact payloads, deployment
  receipts, hardware reports, tag, and published asset;
  and
- package and checksum the supported persistent operator image directly if
  `pluto.frm` is part of the release interface. Optional GitHub provenance may
  describe that same bundle but cannot gate it.

These changes need planted-failure tests. Do not change an acceptance parser or
waiver policy after it has accepted RC10 and continue to claim the earlier
result; either preserve the original verifier with the evidence or rerun the
affected gate under a new candidate commit.

#### A1.6 Defer reduced final confirmation until it has a real runner

A reduced final confirmation is intentionally deferred because no current
repository command emits that verdict. It is not a v8 release path: RC10 and the
final identity both run the full four-radio campaign. A future Track-B change
may add a guarded `scripts/run_tandem_agc_final_confirmation_hardware.sh` (or an
explicit `release_cli` confirmation mode) with offline planted-failure oracles.

For each serial it must require the final candidate index and final
RAM-deployment receipt/DFU SHA, then perform exactly:

- live exact serial, boot ID, firmware, component, FPGA ABI, and TX-safe-state
  verification;
- the authorized TX2-to-both-RX loopback smoke gate;
- one bounded protocol-v3 stream with continuity, metadata, and tandem-state
  validation; and
- verified close, tandem IDLE/FIFO/fault state, TX mute, DDS disable, and ZERO
  selectors.

It writes one immutable `final-confirmation-report.json` per serial and a
four-serial `final-confirmation-index.json` with externally recorded SHA-256.
The command must refuse reduced confirmation unless an offline input-diff
validator proves the qualified RC and final builds differ only in the allowed
release identity/packaging fields. Otherwise it directs the operator to the
full A8 campaign.

The evidence verifier reserves the future producer contract. Canonical
paths are
`hardware/final-confirmation/SERIAL/final-confirmation-report.json` and
`hardware/final-confirmation/final-confirmation-index.json`; schemas are
`plutosdr-fw.tandem-agc-final-confirmation.v1` and
`plutosdr-fw.tandem-agc-final-confirmation-index.v1`. Each serial report has
exact artifact-index, policy, deployment-receipt, DFU, firmware, source, and
four-check bindings (`live_identity`, `tx2_loopback`, `protocol_v3`, `cleanup`),
all `pass`. The aggregate repeats the two parent digests, selects only
`reduced-confirmation`, lists exactly four sorted serials, and rehashes each
report. Until an executable runner emits this exact durable evidence, the
reduced route is unavailable; tests use synthetic records only to plant
verifier failures and never claim a hardware result. The v8 policy always
selects `full-campaign`.

Gate: all Track-A capabilities used by the v8 path have offline planted-failure
tests and pass a one-radio dry run/plan review where applicable; the manifest
and trusted route are committed; and no behavioral source change remains
unreviewed. The deferred reduced runner is not a v8 gate.

### A2. Run the clean-source offline gate

The authoritative PR-equivalent command is:

```bash
PYTHON=python3 ./scripts/check_tandem_release_offline.sh all
```

The script is the same entry point used by the PR workflow. `oracles` runs the
root/radio planted-failure suites, shell syntax checks, and RTL simulations;
`source-graph` checks all v8 manifests and the bounded legal-info network test.
`all` runs both tiers and finishes with `git diff --check`.

Also run the candidate-relevant checks used by the trusted builder:

```bash
./scripts/test_tandem_acquire_sequence.sh
./scripts/test_tandem_detector_latch_clear.sh
./scripts/test_pluto_pstore_layout.sh
./scripts/test_pluto_cma_layout.sh
./scripts/test_winbond_uid_fixup.sh
buildroot/board/pluto/test_pluto_mute_tx.sh
buildroot/board/pluto/test_pluto_boot_safety.sh
buildroot/board/pluto/test_pluto_read_identity.sh
SPF_GAIN_SERIES_MANIFEST="$PWD/manifests/tandem-agc-v8-rc10-source.yaml" \
  ./scripts/build_gain_series_candidate.sh source-check
SPF_GAIN_SERIES_MANIFEST="$PWD/manifests/tandem-agc-v8-rc10-source.yaml" \
  ./scripts/build_gain_series_candidate.sh preflight
SPF_GAIN_SERIES_MANIFEST="$PWD/manifests/tandem-agc-v8-rc10-source.yaml" \
  ./scripts/test_gain_series_hdl.sh
git diff --check
```

The preflight commands require the supported x86-64/Vivado build host and
initialized pinned submodules. Run `bash -n` and ShellCheck on changed shell
scripts and the repository's selected Python formatter/linter on changed Python
files. At present these style gates are not centralized; Track B adds one
authoritative command.

Gate: every command passes on the nominated clean commit, with tool versions and
logs retained. A skip is a failure unless the release checklist names and
justifies it in advance.

### A3. Run routed block-level OOC implementation

The diagnostic RC4-top replacement result in section 2.1 is a capacity result,
not A3 or A5 evidence. It cannot populate `status.txt`, authorize a source
lock, or substitute for the clean commit-bound OOC run and subsequent trusted
RC10 integrated build required below.

Use Vivado 2022.2, a completely clean committed tree, and an absent output path
outside the checkout under an existing non-symlink parent:

```bash
candidate_commit=$(git rev-parse HEAD)
candidate_ooc_parent=$(mktemp -d)
candidate_ooc="$candidate_ooc_parent/tandem-agc-$candidate_commit"
./scripts/run_tandem_agc_ooc.sh \
  "$candidate_ooc"
grep -Fx 'verdict=PASS' "$candidate_ooc/status.txt"
grep -Fx 'scope=tandem_agc_axi_routed_ooc' "$candidate_ooc/status.txt"
grep -Fx 'firmware_release_eligible=false' "$candidate_ooc/status.txt"
grep -Fx 'integrated_route_required=true' "$candidate_ooc/status.txt"
grep -Fx "commit=$candidate_commit" "$candidate_ooc/status.txt"
candidate_manifest_sha=$(sha256sum "$candidate_ooc/evidence-sha256.txt" | awk '{print $1}')
grep -Fx "evidence_manifest_sha256=$candidate_manifest_sha" \
  "$candidate_ooc/status.txt"
(
  cd "$candidate_ooc"
  sha256sum -c evidence-sha256.txt
)
sha256sum "$candidate_ooc/status.txt" \
  > "$candidate_ooc_parent/tandem-agc-$candidate_commit-status.sha256"
```

Retain the input snapshot, source hashes, Vivado/Python versions, routed DCP,
log, timing, route, utilization, CDC summary/details, clock-interaction, DRC,
methodology, input XDC, `timing-metrics.txt`, checksum manifest, `status.txt`,
and the separately stored `status.txt` hash. The current strict OOC inventory
does not emit a bus-skew report or `metrics.json`; those are integrated/Track-B
concepts, respectively.

Gate:

- `status.txt` exists and says `verdict=PASS`;
- setup and hold slack are nonnegative with zero failing endpoints;
- all expected clocks are constrained;
- CDC, clock interaction, DRC, methodology, and route results match the reviewed
  policy with no unknown rule or unreviewed waiver; and
- the evidence hash is recorded in the candidate index with the explicit scope
  `ooc_pass_nonauthorizing`.

### A4. Protect the RC10 source lock and dispatch the trusted build

Only after A0–A3 pass:

1. Verify that the already committed
   `manifests/tandem-agc-v8-rc10-source.yaml` and trusted workflow mapping still
   name the exact graph and candidate branch qualified in A2/A3.
2. Create/push `codex/firmware-tandem-agc-v8-rc10` at the nominated commit and
   freeze it for the candidate build; never force-push it after evidence begins.
3. Create and protect the exact candidate firmware source lock
   `refs/tags/tandem-agc-v8-rc10-source/firmware-v1` at the exact candidate
   commit. Candidate evidence rejects every other ref, including the burned
   RC5 lock and the final lock.
4. Reuse RC4's external dependency pins only after source-graph checks prove
   exact equality; otherwise create new immutable component locks.
5. Fetch and verify every protected ref from the trusted build runner without
   changing the candidate commit.

The source lock is not the annotated candidate/release tag. Do not create an
annotated RC10 release tag until the exact indexed bundle has completed the
required hardware qualification, and never move either kind of ref.

Dispatch the candidate build only after the protected refs are remotely
resolvable:

```bash
gh workflow run firmware-main.yml \
  --repo misko/plutosdr-fw \
  --ref codex/firmware-tandem-agc-v8-rc10 \
  -f release_version=v0.41-plutoplus-spf-tandem-agc-v8-rc10
```

The trusted local entry point used by CI remains:

```bash
scripts/ci/build_main_firmware.sh /absolute/empty/output/outside/checkout
```

CI supplies the manifest, package prefix, release state, `RELEASE_VERSION`,
Vivado 2022.2 environment, and Buildroot cache. Do not improvise a separately
packaged local candidate when the trusted route is available.

Gate: the build is for the intended full commit and source graph; all offline
checks pass; the full Pluto design synthesizes, places, and routes; packaging
finishes; and the immutable Actions artifact is
`plutoplus-main-<40-char-SHA>-<run-id>-<attempt>`.

### A5. Strengthen and review integrated implementation evidence

The integrated route is authoritative. The A1.5 version of
`scripts/ci/package_main_firmware.sh` must retain and check:

- fully routed status and zero routing errors;
- nonnegative WNS/WHS/WPWS and zero failing endpoints;
- no unconstrained or partially constrained release paths;
- complete CDC inventory, not only absence of CDC-10;
- all required bus-skew constraints present and met;
- DRC and methodology severities against a versioned reviewed waiver file;
- no critical warnings in top-level build logs;
- utilization within the agreed Zynq-7010 guardrail, including BRAM/DSP margin;
- the exact routed DCP and generated bitstream hashes; and
- consistency between production parameters and documentation. In particular,
  production currently sets `EVENTS=1`, while the historical integration patch
  and finding still describe `EVENTS=0`.

Gate: every automated check passes and the owner/operator reviews the structured
metrics and any narrow waivers. OOC results cannot be used to excuse an
integrated failure.

### A6. Verify the exact artifact

Download by exact run, attempt, artifact name, and head SHA:

```bash
set -euo pipefail
shopt -s nullglob

candidate_run_id=<run-id>
candidate_commit=<40-character-candidate-commit>
candidate_attempt=<attempt>
candidate_artifact="plutoplus-main-${candidate_commit}-${candidate_run_id}-${candidate_attempt}"
candidate_work=$(mktemp -d)

candidate_ref=refs/heads/codex/firmware-tandem-agc-v8-rc10
gh api "repos/misko/plutosdr-fw/actions/runs/$candidate_run_id" \
  --jq '{schema:"plutosdr-fw.github-actions-run.v1",
         repository:"misko/plutosdr-fw",
         workflow_path:.path,
         ref:("refs/heads/" + .head_branch),
         event:.event,
         id:.id,
         run_attempt:.run_attempt,
         head_sha:.head_sha,
         status:.status,
         conclusion:.conclusion,
         url:.html_url}' \
  > "$candidate_work/actions-run.json"
jq -e --arg ref "$candidate_ref" --arg commit "$candidate_commit" \
  --argjson run "$candidate_run_id" --argjson attempt "$candidate_attempt" \
  '.schema == "plutosdr-fw.github-actions-run.v1" and
   .repository == "misko/plutosdr-fw" and
   .workflow_path == ".github/workflows/firmware-main.yml" and
   .ref == $ref and .event == "workflow_dispatch" and
   .id == $run and .run_attempt == $attempt and
   .head_sha == $commit and .status == "completed" and
   .conclusion == "success"' "$candidate_work/actions-run.json"
test "$(gh run view "$candidate_run_id" --repo misko/plutosdr-fw \
  --json headSha --jq .headSha)" = "$candidate_commit"
gh run download "$candidate_run_id" --repo misko/plutosdr-fw \
  --name "$candidate_artifact" --dir "$candidate_work"

candidate_bundles=("$candidate_work"/*.tar.gz)
candidate_sidecars=("$candidate_work"/*.tar.gz.sha256)
test "${#candidate_bundles[@]}" -eq 1
test "${#candidate_sidecars[@]}" -eq 1
candidate_bundle=${candidate_bundles[0]}
candidate_sidecar=${candidate_sidecars[0]}
test "$candidate_sidecar" = "$candidate_bundle.sha256"
(
  cd "$candidate_work"
  sha256sum -c "$(basename "$candidate_sidecar")"
)

# The v1 artifact contract retains this role even when GitHub attestation is
# deliberately not used. The default single-owner/operator record is exact and
# still binds the repository, run/attempt/head, bundle name, and bundle hash.
candidate_bundle_sha=$(sha256sum "$candidate_bundle" | awk '{print $1}')
jq -n --arg repository misko/plutosdr-fw \
  --arg head_sha "$candidate_commit" \
  --argjson run_id "$candidate_run_id" \
  --argjson run_attempt "$candidate_attempt" \
  --arg bundle "$(basename "$candidate_bundle")" \
  --arg bundle_sha "$candidate_bundle_sha" \
  '{schema:"plutosdr-fw.github-attestation-not-performed.v1",
    repository:$repository, head_sha:$head_sha, run_id:$run_id,
    run_attempt:$run_attempt, bundle_sha256:$bundle_sha,
    subject:{name:$bundle,sha256:$bundle_sha},
    verification_performed:false,
    reason:"single-owner-operator-trust-model"}' \
  > "$candidate_work/attestation-verification.json"

candidate_extracted="$candidate_work/extracted"
mkdir "$candidate_extracted"
tar -xzf "$candidate_bundle" -C "$candidate_extracted"
(
  cd "$candidate_extracted"
  sha256sum -c SHA256SUMS
)
candidate_rootfs_archives=("$candidate_extracted"/*-rootfs.cpio.gz)
test "${#candidate_rootfs_archives[@]}" -eq 1
mkdir "$candidate_extracted/rootfs"
(
  cd "$candidate_extracted/rootfs"
  gzip -dc "${candidate_rootfs_archives[0]}" | \
    cpio -idm --quiet opt/VERSIONS
  cat opt/VERSIONS
)

# Curate the three external source/OOC roles required by the candidate index.
# tandem_release_evidence.py intentionally verifies a pre-populated immutable
# archive; it does not invent these operator records itself.
candidate_evidence_root=/absolute/evidence/tandem-agc-v8-rc10
candidate_ooc=/absolute/path/to/tandem-agc-$candidate_commit
candidate_source_lock=refs/tags/tandem-agc-v8-rc10-source/firmware-v1
test -d "$candidate_ooc"
test "$(git rev-parse "$candidate_source_lock^{commit}")" = "$candidate_commit"
mkdir -p "$candidate_evidence_root/source" "$candidate_evidence_root/evidence"
test ! -e "$candidate_evidence_root/evidence/ooc"
cp -a -- "$candidate_ooc" "$candidate_evidence_root/evidence/ooc"
install -m 0644 manifests/tandem-agc-v8-rc10-source.yaml \
  "$candidate_evidence_root/source/tandem-agc-v8-rc10-source.yaml"
install -m 0644 "$candidate_ooc/evidence-sha256.txt" \
  "$candidate_evidence_root/evidence/evidence-sha256.txt"
install -m 0644 "$candidate_ooc/status.txt" \
  "$candidate_evidence_root/evidence/ooc-status.txt"

{
  printf 'schema=plutosdr-fw.source-lock.v1\n'
  printf 'ref=%s\n' "$candidate_source_lock"
  printf 'commit=%s\n' "$candidate_commit"
} > "$candidate_evidence_root/evidence/source-lock.txt"

# This role is an operator record composed deterministically from the two exact
# OOC producer outputs. The full original files remain under evidence/ooc/.
{
  printf 'schema=plutosdr-fw.source-tool-hashes.v1\n'
  printf 'input_sha256_file_sha256=%s\n' \
    "$(sha256sum "$candidate_ooc/input-sha256.txt" | awk '{print $1}')"
  printf 'provenance_file_sha256=%s\n' \
    "$(sha256sum "$candidate_ooc/provenance.txt" | awk '{print $1}')"
  printf '%s\n' '--- input-sha256.txt ---'
  cat "$candidate_ooc/input-sha256.txt"
  printf '%s\n' '--- provenance.txt ---'
  cat "$candidate_ooc/provenance.txt"
} > "$candidate_evidence_root/evidence/source-and-tool-hashes.txt"

cmp manifests/tandem-agc-v8-rc10-source.yaml \
  "$candidate_evidence_root/source/tandem-agc-v8-rc10-source.yaml"
test "$(wc -l < "$candidate_evidence_root/evidence/source-lock.txt")" -eq 3
```

In addition, require:

- `device-fw` exactly equals the candidate identity;
- packed HDL, Buildroot, Linux, and U-Boot identities exactly match the source
  manifest;
- DFU suffix/vendor/product/length checks are mandatory, not silently skipped
  when `dfu-suffix` is missing;
- FIT, FPGA bitstream, rootfs, XSA, and bundle hashes are retained;
- all routed reports and build provenance are present; and
- the harness commit/hash and deployment receipt schema version are recorded.

Gate: a candidate evidence index binds source lock, manifest hash, OOC evidence,
CI run/attempt/head SHA, the supporting attestation record, bundle,
DFU/FIT/rootfs/bitstream hashes,
and expected runtime identities. No device is booted before this index passes
offline validation. The authorizing check is:

```bash
python3 scripts/tandem_release_evidence.py assemble \
  --stage candidate-pre-hardware \
  --archive-root /absolute/evidence/tandem-agc-v8-rc10 \
  --input /absolute/evidence/tandem-agc-v8-rc10/candidate-index-input.json \
  --output /absolute/evidence/tandem-agc-v8-rc10/candidate-index.json
python3 scripts/tandem_release_evidence.py verify \
  --stage candidate-pre-hardware \
  --index /absolute/evidence/tandem-agc-v8-rc10/candidate-index.json
```

`assemble` also writes the detached `.sha256` sidecar. Both commands refuse an
unknown schema/stage, a missing required member, a digest mismatch, a path that
escapes the archive root, or an input whose embedded commit/identity disagrees
with the requested stage. The verifier streams the tar.gz without extracting
it, rejects links/special files/duplicates/non-flat paths and size/count bombs,
requires exact sorted `SHA256SUMS` and `PAYLOAD_SHA256SUMS` coverage, and proves
that the indexed source manifest, DFU/FIT, rootfs, XSA, routed DCP/reports, and
waiver/verdict bytes are the corresponding members of the indexed bundle.
The source manifest must be at the canonical `source/tandem-agc-v8-*-source.yaml`
archive path and byte-equal to `manifests/<same-basename>` at the indexed commit;
an external same-named manifest is rejected. The integrated PASS verdict's
ordered `validated_inputs` descriptors must exactly bind the manifest, waiver,
DCP, utilization, timing, route-status, DRC, methodology, CDC, and bus-skew
bytes, so a stale PASS cannot authorize substituted routed reports.

The default exact `plutosdr-fw.github-attestation-not-performed.v1` record has
`verification_performed=false` and
`reason=single-owner-operator-trust-model`. The verifier also accepts the exact
`plutosdr-fw.github-attestation-verification.v1` capture, including the real
machine-readable `gh attestation verify --format json` result, when an operator
chooses to create one. That capture is supporting metadata only: neither variant
is treated as independent signature or DSSE authentication. Offline replay
checks its repository, run/attempt/head, subject, and bundle identities and
resolves the local protected source tag. Record the detached index digest with
the release checklist or archived campaign evidence.

The trusted workflow ends after the build job uploads the exact bundle and its
detached checksum. It has no required GitHub-attestation job. An operator who
chooses the optional captured form does so as a separate supporting-evidence
step; failure or absence of that step cannot change the build result.

Hardware consumers must call the read-only
`verify_artifact_index_semantics(index_path, expected_stage=...)` API before
they derive a plan or open USB. The verifier source itself is a mandatory
live/committed/indexed harness member. Under the explicit single-owner/operator
threat model, that API authorizes only after resolving the exact local source
lock and committed verifier and reproducing all run/attempt, bundle checksum,
member, DFU/FIT, and evidence-role bindings. Dummy or substituted bytes fail
closed. The API makes no cryptographic-attestation claim and does not require a
newer GitHub CLI.

### A7. RAM-boot the exact candidate on all four radios

Use only the A1.3 guarded deployer and run one serial at a time. The deployment
receipt for each radio must bind:

- the exact candidate evidence index and DFU hash;
- exact serial and pre/post USB topology, Pluto+ hardware model, runtime
  `fw_version`, and distinct pre/post boot IDs;
- the required live IIO devices and final TX mute, DDS, selector, and tandem
  state (the candidate index separately binds packed component and FPGA ABI
  evidence); and
- a read-only digest/identity of the firmware QSPI partition before and after
  RAM boot, proving it did not change;
- the exact temporary `192.168.2.1/32` route/interface/source lease and verified
  removal before receipt publication; and
- the strict known-hosts digest and transparent SSH command path, including
  the password-file pathname but never its contents or a derived digest.

Create the password file outside the evidence archive, mode 0600, and never
place its value on the command line. First run the offline planner without
`--execute`; it validates the private file and records only its pathname in the
reviewable command plan, never prints its contents, and opens no hardware.
Then run the same exact inputs with `--execute` and the serial-bound phrase:

```bash
scripts/deploy_tandem_agc_ram_hardware.sh \
  --radio-serial SERIAL \
  --artifact /absolute/evidence/tandem-agc-v8-rc10/artifact/EXACT-RC10.dfu \
  --artifact-sha256 DFU_SHA256 \
  --artifact-index /absolute/evidence/tandem-agc-v8-rc10/candidate-index.json \
  --artifact-index-sha256 CANDIDATE_INDEX_SHA256 \
  --expected-current-firmware EXACT_CURRENT_FIRMWARE \
  --receipt /absolute/evidence/tandem-agc-v8-rc10/hardware/deploy/SERIAL/ram-boot-receipt.json \
  --known-hosts /absolute/private/SERIAL.known_hosts \
  --known-hosts-sha256 KNOWN_HOSTS_SHA256 \
  --ssh-password-file /absolute/private/SERIAL.password \
  --usb-interface EXACT_INTERFACE \
  --usb-inventory /absolute/private/usb-inventory.json

scripts/deploy_tandem_agc_ram_hardware.sh \
  --radio-serial SERIAL \
  --artifact /absolute/evidence/tandem-agc-v8-rc10/artifact/EXACT-RC10.dfu \
  --artifact-sha256 DFU_SHA256 \
  --artifact-index /absolute/evidence/tandem-agc-v8-rc10/candidate-index.json \
  --artifact-index-sha256 CANDIDATE_INDEX_SHA256 \
  --expected-current-firmware EXACT_CURRENT_FIRMWARE \
  --receipt /absolute/evidence/tandem-agc-v8-rc10/hardware/deploy/SERIAL/ram-boot-receipt.json \
  --known-hosts /absolute/private/SERIAL.known_hosts \
  --known-hosts-sha256 KNOWN_HOSTS_SHA256 \
  --ssh-password-file /absolute/private/SERIAL.password \
  --usb-interface EXACT_INTERFACE \
  --usb-inventory /absolute/private/usb-inventory.json \
  --operator-confirmation "RAM BOOT SERIAL" \
  --execute
```

If the pre/post QSPI readback, route verification/removal, authentication,
identity, topology, or cleanup check is unavailable, execution fails and no v3
receipt is published.

Candidates remain RAM-only. A power cycle is the normal rollback to the known
good persistent image.

Gate: four valid receipts exist, one per release-gate serial, and the hardware
runner can independently re-attest every receipt and live identity.

### A8. Run candidate hardware qualification

#### Fixture and preflight

For each radio:

- wire TX2 through the measured attenuation/backoff path to both RX inputs;
- require at least 30 dB effective attenuation to each receiver at the strongest
  commanded TX setting;
- use the exact serial, local USB context, candidate firmware identity,
  candidate deployment receipt, and manifest-pinned host libiio;
- verify both RX branches with a bounded tone before adaptive testing; and
- begin with TX1/TX2 muted, all DDS channels disabled, and all four DAC
  selectors at ZERO.

The release orchestrator's `--firmware-version` is a literal exact line, not a
regular expression. Its existing `--artifact-index` and
`--deployment-receipt` inputs bind the exact RAM deployment. First render and
review the fully expanded plan without opening USB:

```bash
IIO_MANIFEST=manifests/tandem-agc-v8-rc10-source.yaml \
IIO_SOURCE=../libiio \
PYTHON=.venv-radio-hardware/bin/python \
scripts/run_tandem_agc_release_hardware.sh \
  --authorize-tx2-loopback \
  --radio-serial SERIAL \
  --firmware-version v0.41-plutoplus-spf-tandem-agc-v8-rc10 \
  --artifact-index /absolute/evidence/tandem-agc-v8-rc10/candidate-index.json \
  --deployment-receipt /absolute/evidence/tandem-agc-v8-rc10/hardware/deploy/SERIAL/ram-boot-receipt.json \
  --physical-attenuation-db ATTENUATION \
  --output /absolute/evidence/tandem-agc-v8-rc10/hardware/full \
  --plan-only
```

Then repeat without `--plan-only`. By default the aggregate runs all three
release phases—steady, transient, and modulated—at 915 MHz, 2.45 GHz, and
5.8 GHz. The full steady phase runs baseline plus controlled one-factor sweeps
for low-power threshold, large-LMT threshold, ADC thresholds, dwell, and
cooldown. It covers manual, native slow attack, native fast attack, and tandem
AUTO according to each phase's release policy.

Run the baseline repeatability soak in a different output root; reusing the
full-characterization root correctly fails checkpoint fingerprint validation:

```bash
IIO_MANIFEST=manifests/tandem-agc-v8-rc10-source.yaml \
IIO_SOURCE=../libiio \
PYTHON=.venv-radio-hardware/bin/python \
scripts/run_tandem_agc_release_hardware.sh \
  --authorize-tx2-loopback \
  --radio-serial SERIAL \
  --firmware-version v0.41-plutoplus-spf-tandem-agc-v8-rc10 \
  --artifact-index /absolute/evidence/tandem-agc-v8-rc10/candidate-index.json \
  --deployment-receipt /absolute/evidence/tandem-agc-v8-rc10/hardware/deploy/SERIAL/ram-boot-receipt.json \
  --physical-attenuation-db ATTENUATION \
  --output /absolute/evidence/tandem-agc-v8-rc10/hardware/soak \
  --phase steady \
  --policy-set baseline
```

Baseline defaults are four cycles, a 1,200-second interval, and a 5,400-second
deadline. Default resume is intentional. `--retry-failed` explicitly authorizes
a fresh attempt after a recorded failed phase; `--no-resume` is only valid with
no existing checkpoint.

The executable gate matrix is:

| Gate | Entry point/status before A1 | RC10 output | Required on RC10 |
|---|---|---|---|
| Full steady/transient/modulated characterization | Existing candidate-bound `scripts/run_tandem_agc_release_hardware.sh` | `hardware/full/SERIAL/release-hardware-report.json` plus phase sidecars | All four radios |
| Baseline repeatability soak | Existing release runner with `--phase steady --policy-set baseline` | `hardware/soak/SERIAL/release-hardware-report.json` | All four radios |
| Muted 64-frame lifecycle | Existing generalized, candidate-bound `scripts/run_muted_metadata_batch_lifecycle_hardware.sh` | `hardware/lifecycle/SERIAL/muted-metadata-batch-lifecycle-v5.json` and raw sidecars | All four radios |
| Stale-small-ADC internal FSM diagnostic | Current observer emits only `BLOCKED` v1; optional diagnostic/TODO, never a promotion phase | Optional `hardware/stale-latch/SERIAL/stale-latch-report.json` retained as a raw member | Not release-authorizing; deterministic RTL proves the property at both supported clock ratios |
| Final full campaign | Existing candidate-bound release and lifecycle runners, repeated against the final artifact index and receipts | Final `hardware/{full,soak,lifecycle}/SERIAL/...` reports | Final build only, all four radios |

The generalized muted lifecycle command retains its guarded shape and accepts
exact candidate inputs rather than embedded RC4 constants:

```bash
IIO_SOURCE=../libiio \
PYTHON=.venv-radio-hardware/bin/python \
scripts/run_muted_metadata_batch_lifecycle_hardware.sh \
  --hardware \
  --source-manifest /absolute/evidence/tandem-agc-v8-rc10/source/tandem-agc-v8-rc10-source.yaml \
  --artifact-index /absolute/evidence/tandem-agc-v8-rc10/candidate-index.json \
  --deployment-receipt /absolute/evidence/tandem-agc-v8-rc10/hardware/deploy/SERIAL/ram-boot-receipt.json \
  --candidate-dfu /absolute/evidence/tandem-agc-v8-rc10/artifact/plutoplus-spf-tandem-agc-v8-rc10-COMMIT-pluto.dfu \
  --serial SERIAL \
  --output /absolute/evidence/tandem-agc-v8-rc10/hardware/lifecycle/SERIAL/muted-metadata-batch-lifecycle-v5.json
```

The stale-latch observer may be improved later as a diagnostic, but release
authorization does not depend on it. The internal re-arm, one-pulse-per-episode,
bounded-clear, HOLD, and failure behavior is authoritatively covered by
deterministic RTL tests at both supported clock ratios. The hardware campaign
covers externally observable paired behavior, transient/modulated operation,
lifecycle, and safety.

Zero-cooldown/HOLD handoff, FIFO overflow visibility, reset ordering, and
legacy/no-session behavior remain mandatory in the RTL/offline release gate.
Do not claim separate hardware evidence for them unless a guarded phase and
durable report actually exist. Host `SIGKILL`, cable/device loss, ENSM
disturbance, watchdog/iiOD restart, and deliberate hardware FIFO-pressure
injection remain valuable post-v8 fault-campaign work; promote any of them into
RC10 only by implementing its runner/oracles before A2 and adding it explicitly
to this matrix.

Gate: every serial's durable aggregate report says `verdict=pass`; every
requested phase is complete; every separate lifecycle report passes;
all reports bind the expected deployment receipt and DFU SHA; there are no
unexplained event/sequence gaps, unpaired indexes, unsafe flags, overflow,
faults, stuck ownership, or cleanup failures.

### A9. Reject, recover, or promote the candidate

On any failure:

1. stop the campaign for the affected serial;
2. execute and verify all independent mute/selector/release cleanup paths;
3. preserve the failed report, raw logs, artifact identity, and fixture state;
4. power-cycle to the known-good QSPI image;
5. attest the stable serial, version, boot ID, and TX-safe state; and
6. classify the failure before changing source or rerunning.

Do not overwrite a failed report or use `--retry-failed` until the failure is
understood and the rerun is explicitly authorized. A functional fix becomes a
new candidate; an invalid fixture/evidence run may be repeated with the same
bytes only after documenting why the prior evidence was non-qualifying.

After all four serials pass, assemble and verify the immutable promotion layer:

```bash
python3 scripts/tandem_release_evidence.py assemble \
  --stage candidate-qualified \
  --archive-root /absolute/evidence/tandem-agc-v8-rc10 \
  --parent-index /absolute/evidence/tandem-agc-v8-rc10/candidate-index.json \
  --output /absolute/evidence/tandem-agc-v8-rc10/campaign-index.json
python3 scripts/tandem_release_evidence.py verify \
  --stage candidate-qualified \
  --index /absolute/evidence/tandem-agc-v8-rc10/campaign-index.json
```

Promote only when `campaign-index.json` covers all four deployment receipts,
the current full/soak/lifecycle report schemas, cleanup evidence, and every raw
sidecar, and its digest is recorded in the operator review. Promotion rehashes
the reports and raw members and cross-binds the exact candidate index, receipt,
serial, committed runner/harness, host libiio, canonical phase plan, and cleanup
results. This is an operator-owned coherence check, not a cryptographic trust
or archive-forensics system. A retained `BLOCKED` stale-small-ADC observer
report is an optional diagnostic raw member and cannot affect promotion.

### A10. Build and confirm the final v8 identity

1. Merge the exact qualified candidate source to `main` without adding a
   functional change. Before dispatching the final build, create and push the
   exact immutable final firmware source lock
   `refs/tags/tandem-agc-v8-source/firmware-v1` at that exact main commit—even
   when a fast-forward makes it the same object as RC10. Final evidence rejects
   the RC10 candidate ref:

```bash
set -euo pipefail
exact_main_commit='<40-character-exact-main-commit>'
[[ "$exact_main_commit" =~ ^[0-9a-f]{40}$ ]]
git tag tandem-agc-v8-source/firmware-v1 "$exact_main_commit"
git push origin tandem-agc-v8-source/firmware-v1
test "$(git rev-parse refs/tags/tandem-agc-v8-source/firmware-v1^{commit})" = \
  "$(git rev-parse "$exact_main_commit^{commit}")"
```

   Do not move or reuse
   `refs/tags/tandem-agc-v8-rc10-source/firmware-v1`. `source-lock.txt` for the
   final artifact records the exact final ref; a merge commit cannot be
   validated against the RC10 source lock.
2. Dispatch `main` with
   `release_version=v0.41-plutoplus-spf-tandem-agc-v8`.
3. Verify the main run's head SHA, supporting attestation record, bundle, inner
   checksums, packed component versions, and exact final `device-fw` as in A6.
4. Compare candidate and final Git trees and emit
   `candidate-to-final-diff.json` with schema
   `plutosdr-fw.tandem-candidate-to-final-diff`, version 1. It records both
   commits/tree IDs plus a unique sorted added/deleted/modified path and blob-ID
   inventory; equal trees require an empty inventory and unequal trees require
   a nonempty inventory. Assembly and every replay resolve both exact commits
   locally and reproduce `git diff-tree -r --no-renames --raw --no-abbrev`;
   supplied fake tree IDs, omitted/extra paths, wrong blob IDs, and inferred
   rename records are rejected. If either Git object is unavailable, source
   identity is unproven and the full campaign remains required.
5. Assemble and verify the plain v1 `final-artifact-index.json` with stage
   `final-pre-confirmation`; this remains the exact hardware-consumed artifact
   contract. Do not add lineage fields to it. Then assemble its strict
   `final-qualification-policy.json` companion. The companion binds the final
   artifact, the qualified RC campaign index, and the diff bytes; independently
   compares release invariants, all source-manifest pins, and harness hashes;
   and records `required_test=full-campaign`. The reduced-confirmation schema is
   reserved for a later executable runner and cannot authorize v8:

```bash
python3 scripts/tandem_release_evidence.py assemble \
  --stage final-pre-confirmation \
  --archive-root /absolute/evidence/tandem-agc-v8-final \
  --input /absolute/evidence/tandem-agc-v8-final/final-index-input.json \
  --output /absolute/evidence/tandem-agc-v8-final/final-artifact-index.json
python3 scripts/tandem_release_evidence.py assemble \
  --stage final-qualification-policy \
  --archive-root /absolute/evidence/tandem-agc-v8-final \
  --parent-index /absolute/evidence/tandem-agc-v8-final/final-artifact-index.json \
  --candidate-qualified-index /absolute/evidence/tandem-agc-v8-final/lineage/rc10/campaign-index.json \
  --diff /absolute/evidence/tandem-agc-v8-final/candidate-to-final-diff.json \
  --output /absolute/evidence/tandem-agc-v8-final/final-qualification-policy.json
python3 scripts/tandem_release_evidence.py verify \
  --stage final-qualification-policy \
  --index /absolute/evidence/tandem-agc-v8-final/final-qualification-policy.json
```

   Copy the complete immutable RC10 archive beneath `lineage/rc10/`; copying only
   its campaign index is insufficient because recursive verification rehashes
   its parent artifact, reports, receipts, and raw members.
6. Repeat the full A7/A8 campaign on the final bytes. Pass
   `final-artifact-index.json` through `--artifact-index`, create new
   final-artifact-bound deployment receipts, and keep all four radios' full,
   soak, lifecycle, cleanup, and raw outputs under the final evidence root.
   Candidate-to-final tree equality is useful review evidence, but it does not
   reduce the v8 hardware matrix because no guarded reduced-confirmation runner
   currently exists.
7. Assemble and verify `final-qualification-index.json` with stage
   `final-qualified`, parent `final-artifact-index.json`, and the policy
   companion. For v8 the assembler requires `required_test=full-campaign` and
   accepts only the complete four-radio A8 matrix. It rejects reduced, mixed,
   stale, or incomplete evidence.

```bash
python3 scripts/tandem_release_evidence.py assemble \
  --stage final-qualified \
  --archive-root /absolute/evidence/tandem-agc-v8-final \
  --parent-index /absolute/evidence/tandem-agc-v8-final/final-artifact-index.json \
  --policy-index /absolute/evidence/tandem-agc-v8-final/final-qualification-policy.json \
  --output /absolute/evidence/tandem-agc-v8-final/final-qualification-index.json
```
8. Only after the final qualification index passes, create the annotated
   release tag on the built main commit:

```bash
set -euo pipefail
umask 0022
built_main_commit='<40-character-built-main-commit>'
release_tag=v0.41-plutoplus-spf-tandem-agc-v8
evidence_root=/absolute/evidence/tandem-agc-v8-final
git tag -a v0.41-plutoplus-spf-tandem-agc-v8 \
  "$built_main_commit" -m 'Tandem AGC v8'
git push origin v0.41-plutoplus-spf-tandem-agc-v8

# Retain the exact local annotated object and its commit target. This records
# object identity only; it deliberately makes no signature claim.
tag_ref="refs/tags/$release_tag"
tag_object=$(git rev-parse --verify "$tag_ref")
tag_object_type=$(git cat-file -t "$tag_object")
tag_target=$(git rev-parse --verify "$tag_ref^{commit}")
tag_target_type=$(git cat-file -t "$tag_target")
test "$tag_object_type" = tag
test "$tag_target_type" = commit
test "$tag_target" = "$built_main_commit"
jq -n --arg name "$release_tag" --arg object_id "$tag_object" \
  --arg target_commit "$tag_target" \
  '{schema:"plutosdr-fw.annotated-tag-record.v1",name:$name,
    object_type:"tag",object_id:$object_id,target_type:"commit",
    target_commit:$target_commit,
    signature_verification:"not-performed-or-claimed"}' \
  > "$evidence_root/annotated-tag-record.json"

# Capture the canonical remote tag ref and its annotated-tag peel once, before
# offline assembly. The retained JSON is hashed by the published index; replay
# performs no network access.
remote_repo=https://github.com/misko/plutosdr-fw.git
remote_peeled_ref="$tag_ref^{}"
git ls-remote --tags "$remote_repo" "$tag_ref" "$remote_peeled_ref" \
  > "$evidence_root/github-remote-tag.raw.txt"
awk -F '\t' 'NF != 2 {exit 1} END {if (NR != 2) exit 1}' \
  "$evidence_root/github-remote-tag.raw.txt"
jq -Rn --arg repo "$remote_repo" --arg tag_ref "$tag_ref" \
  --arg peeled_ref "$remote_peeled_ref" \
  '[inputs | split("\t") | {object_id:.[0],ref:.[1]}] as $refs |
   {schema:"plutosdr-fw.git-remote-tag-record.v1",
    command:["git","ls-remote","--tags",$repo,$tag_ref,$peeled_ref],
    exit_code:0,refs:$refs}' \
  < "$evidence_root/github-remote-tag.raw.txt" \
  > "$evidence_root/github-remote-tag-record.json"
jq -e --arg object "$tag_object" --arg target "$tag_target" \
  --arg tag_ref "$tag_ref" --arg peeled_ref "$remote_peeled_ref" \
  '.refs == [{object_id:$object,ref:$tag_ref},
             {object_id:$target,ref:$peeled_ref}]' \
  "$evidence_root/github-remote-tag-record.json"
```

9. Publish the exact already-qualified DFU, `pluto.frm`, and bundle as a
   non-draft, non-prerelease under the canonical
   `misko/plutosdr-fw` tag. Never rebuild them. Capture the remote inventory
   after upload; this is a practical exact three-asset name/size/SHA-256/URL
   check, not a signature claim:

```bash
set -euo pipefail
umask 0022
release_tag=v0.41-plutoplus-spf-tandem-agc-v8
evidence_root=/absolute/evidence/tandem-agc-v8-final
inventory_endpoint="repos/misko/plutosdr-fw/releases/tags/$release_tag"
inventory_jq='{tagName:.tag_name,isDraft:.draft,isPrerelease:.prerelease,url:.html_url,assets:[.assets[]|{name,size,state,url:.browser_download_url,digest}]}'
gh api "$inventory_endpoint" --jq "$inventory_jq" \
  > "$evidence_root/github-release-view.raw.json"
jq -n --slurpfile result "$evidence_root/github-release-view.raw.json" \
  --arg endpoint "$inventory_endpoint" --arg inventory_jq "$inventory_jq" \
  '{schema:"plutosdr-fw.github-release-inventory.v1",
    command:["gh","api",$endpoint,"--jq",$inventory_jq],
    exit_code:0,result:$result[0]}' \
  > "$evidence_root/github-release-inventory.json"
test ! -e "$evidence_root/published"
mkdir -m 0755 "$evidence_root/published"
gh release download "$release_tag" --repo misko/plutosdr-fw \
  --dir "$evidence_root/published"
```
10. Create `manifests/tandem-agc-v8.yaml` from the published bytes, including all
   required `verify_release.sh` fields plus source refs, CI identity, the exact
   supporting-attestation record (the not-performed form is normal), routed
   evidence, four-radio receipts/reports, and the selected
   final-qualification hashes. The published-stage verifier requires every
   field consumed by `verify_release.sh`: gadget and submodule identities, all
   packed `VERSIONS` pins, FPGA and ramdisk MD5 values, and FIT description, in
   addition to the release/asset identities. It binds gadget/submodule/version
   fields back to the qualified source manifest and binds the verifier result's
   gadget/FPGA values back to this exact release manifest. Copy those exact
   bytes to the evidence root for the remote verification command and prove the
   two copies agree:

```bash
install -m 0644 manifests/tandem-agc-v8.yaml \
  "$evidence_root/tandem-agc-v8.yaml"
cmp manifests/tandem-agc-v8.yaml "$evidence_root/tandem-agc-v8.yaml"
```
11. Verify a fresh remote download, not the pre-upload local DFU. Start with an
    absent `remote-verification-cache/`; `verify_release.sh` downloads from the
    canonical manifest URL because `--image` is deliberately omitted. Retain
    the downloaded DFU and the exact schema-v1 JSON wrapper of the command,
    indexed verifier digest, manifest digest, exit status, and unmodified
    `--json` result. The wrapper's `verifier_sha256` is checked against the
    final artifact's exact harness inventory during offline replay:

```bash
set -euo pipefail
umask 0022
repo_root=/absolute/path/to/plutosdr-fw
cd /absolute/evidence/tandem-agc-v8-final
test ! -e remote-verification-cache

# Bind the program that interprets the manifest/result. The final artifact
# harness already indexes its archived bytes; publication requires those bytes
# to equal both the live invocation and the file at the qualified final commit.
final_commit=$(jq -er '.source.commit' final-artifact-index.json)
test "$(jq '[.harness.files[] |
              select(.path == "scripts/verify_release.sh")] | length' \
              final-artifact-index.json)" -eq 1
indexed_verifier_sha256=$(jq -er \
  '.harness.files[] | select(.path == "scripts/verify_release.sh") | .sha256' \
  final-artifact-index.json)
archived_verifier_sha256=$(sha256sum scripts/verify_release.sh | awk '{print $1}')
live_verifier_sha256=$(sha256sum "$repo_root/scripts/verify_release.sh" | \
  awk '{print $1}')
committed_verifier_sha256=$(git --no-replace-objects -C "$repo_root" \
  show "${final_commit}:scripts/verify_release.sh" | sha256sum | awk '{print $1}')
test "$indexed_verifier_sha256" = "$archived_verifier_sha256"
test "$indexed_verifier_sha256" = "$live_verifier_sha256"
test "$indexed_verifier_sha256" = "$committed_verifier_sha256"

env VERIFY_RELEASE_CACHE=remote-verification-cache \
  "$repo_root/scripts/verify_release.sh" tandem-agc-v8.yaml --json \
  > release-verification.raw.json
# Wrap the successful result without editing it. The record normalizes the
# committed verifier path to its repository-relative entry point.
jq -n --slurpfile result release-verification.raw.json \
  --arg verifier_sha256 "$indexed_verifier_sha256" \
  --arg manifest_sha256 "$(sha256sum tandem-agc-v8.yaml | awk '{print $1}')" \
  '{schema:"plutosdr-fw.release-verification.v1",
    command:["env","VERIFY_RELEASE_CACHE=remote-verification-cache",
             "scripts/verify_release.sh","tandem-agc-v8.yaml","--json"],
    exit_code:0,verifier_sha256:$verifier_sha256,
    manifest_sha256:$manifest_sha256,result:$result[0]}' \
  > release-verification.json
```

12. Assemble and verify `published-release-index.json` with stage
    `published-release`. It must bind the final-artifact index, four deployment
    receipts, `final-qualification-index.json` and its selected report set, the
    annotated tag, canonical release URL, captured GitHub asset inventory,
    release manifest, published asset digests, the separately downloaded DFU,
    and the successful binary-verifier result. `published-input.json` names
    `remote_tag_record_path`, `release_inventory_path`, and
    `verification_image_path` in addition to the three published asset paths.
    Record the final detached digest in the release notes. Its local annotated-
    tag record and retained remote-tag record must agree on the exact tag object
    ID, and both the local peel and remote `^{}` ref must equal the qualified
    final commit. The v1 local record says
    `signature_verification=not-performed-or-claimed`; this tooling verifies an
    annotated object/target but does not claim signed-tag support. The verifier
    consumes only retained hash-indexed files during assembly/replay and does
    not contact GitHub.

```bash
set -euo pipefail
umask 0022
repo_root=/absolute/path/to/plutosdr-fw
cd /absolute/evidence/tandem-agc-v8-final
shopt -s nullglob
published_dfus=(published/*-pluto.dfu)
published_frms=(published/*-pluto.frm)
published_bundles=(published/*.tar.gz)
test "${#published_dfus[@]}" -eq 1
test "${#published_frms[@]}" -eq 1
test "${#published_bundles[@]}" -eq 1
release_tag=v0.41-plutoplus-spf-tandem-agc-v8
release_url="https://github.com/misko/plutosdr-fw/releases/download/$release_tag"
verification_image="remote-verification-cache/${published_dfus[0]##*/}"
test -f "$verification_image"
jq -n --arg release_url "$release_url" \
  --arg tag_record_path annotated-tag-record.json \
  --arg remote_tag_record_path github-remote-tag-record.json \
  --arg dfu_path "${published_dfus[0]}" \
  --arg frm_path "${published_frms[0]}" \
  --arg bundle_path "${published_bundles[0]}" \
  --arg release_inventory_path github-release-inventory.json \
  --arg release_manifest_path tandem-agc-v8.yaml \
  --arg verification_image_path "$verification_image" \
  --arg verification_result_path release-verification.json \
  '{schema:"plutosdr-fw.tandem-published-release-input",
    schema_version:1,stage:"published-release",release_url:$release_url,
    tag_record_path:$tag_record_path,
    remote_tag_record_path:$remote_tag_record_path,
    dfu_path:$dfu_path,frm_path:$frm_path,bundle_path:$bundle_path,
    release_inventory_path:$release_inventory_path,
    release_manifest_path:$release_manifest_path,
    verification_image_path:$verification_image_path,
    verification_result_path:$verification_result_path}' \
  > published-input.json

python3 "$repo_root/scripts/tandem_release_evidence.py" assemble \
  --stage published-release \
  --archive-root /absolute/evidence/tandem-agc-v8-final \
  --parent-index /absolute/evidence/tandem-agc-v8-final/final-qualification-index.json \
  --input /absolute/evidence/tandem-agc-v8-final/published-input.json \
  --output /absolute/evidence/tandem-agc-v8-final/published-release-index.json
python3 "$repo_root/scripts/tandem_release_evidence.py" verify \
  --stage published-release \
  --index /absolute/evidence/tandem-agc-v8-final/published-release-index.json
```
13. Update `RELEASE_NOTES.md` and the relevant build, flashing, hardware, and
    design documents with the final source/tag, CI run/attempt, artifact hashes,
    integrated timing/CDC/DRC summary, four-radio evidence-index hash, final
    qualification mode/result, installation method, rollback, and known
    limitations. If the final run-derived values require a post-tag
    documentation commit, keep it documentation-only, identify the built/tagged
    commit explicitly, and never move the tag or rebuild the asset.

Gate: the local and canonical-remote annotated tag object/peeled commit,
published asset, source commit, `device-fw`, immutable manifest, exact binary
verifier hash, supporting attestation record, hardware evidence, and release
documentation all describe the same bytes.

### A11. Persistent deployment after release

Persistent rollout is distinct from publishing the release and is blocked until
the exact-serial persistent installer/receipt work in P2-3 is implemented and
reviewed. The A1.3 RAM deployer must not be repurposed to authorize a QSPI
write. Until P2-3 exists, [flashing.md](flashing.md) is suitable only as a
manual procedure with exactly one isolated radio; it is not an auditable fleet
rollout.

1. Retain and hash the currently approved QSPI firmware for rollback.
2. Power-cycle the selected canary back to QSPI; do not infer QSPI content from
   `/opt/VERSIONS` while a RAM image is active.
3. Install only the firmware partition using the published, verified release
   asset. Never update bootloader/environment or use a full ZIP during a routine
   rollout.
4. Remove power completely, reconnect, and verify the cold-booted serial,
   `device-fw`, packed components, gadget identity, 2R2T mode, CMA, FPGA
   identity, TX mute, DDS/selector state, IIO discovery, RX smoke, tandem
   acquire/HOLD/AUTO/release, and cleanup.
5. Keep the canary under observation before rolling the remaining radios in
   controlled batches.
6. Produce a persistent-install receipt for each serial.

The release bundle should directly include and checksum the supported
operator-facing persistent image such as `pluto.frm`; optional provenance, when
requested, describes that same bundle. Requiring an operator to convert the
qualified DFU creates avoidable provenance risk. P2-3 must refuse to
run unless this published image, its checksum, and release manifest are exact.

If a firmware-partition install fails but the bootloader still enters DFU,
restore the known-good firmware partition. Bootloader recovery is a separate,
board-specific procedure and must not be improvised during rollout.

## 5. Track B — post-v8 refactoring and robustness

Track B begins from the protected v8 source/tag and captured golden evidence.
The first refactor release is not v8 and receives fresh routed/hardware
qualification appropriate to its changes.

### B0. Build a stable verification boundary

Before moving RTL:

- add a test-only observation interface or wrapper exposing named architectural
  events—detector sample accepted, decision accepted, pulse started/completed,
  index committed, event committed, lifecycle transition, and fault—so tests no
  longer reach into implementation registers;
- capture cycle-level golden traces from the v8 core for every directed test and
  fixed stress seed;
- build a lockstep testbench that drives the protected v8 reference core and the
  refactored core with identical inputs and compares public outputs plus the
  architectural observation interface;
- make randomized seeds explicit, reproducible, printed on failure, and retained
  as regression cases;
- add ABI request/register/event golden vectors independent of the runtime
  encoder; and
- preserve representative hardware detector/metadata traces for offline replay;
  and
- add an initial formal reference harness for the unmodified v8 core, proving
  the decision-acceptance guard, accepted-decision/pulse/index/event-write
  relationship, stale-clear budget, lifecycle safety, and FIFO overflow
  visibility before any module extraction.

Gate: the unmodified v8 implementation passes the new boundary and reproduces
all stored traces before any module extraction.

### B1. Target RTL architecture

The target data/control flow is:

```text
asynchronous detector inputs
        |
        v
detector conditioner + delivered-sample timebase
        |
        v
dwell + stale-latch episode state tracker
        |
        v
side-effect-free policy decoder
        |  decision(valid, direction, reason, next_index)
        v
decision acceptance (`decision_accept = valid && ready`)
        |
        +----> pulse engine ----> started / completed
        +----> atomic index, transition, and diagnostic commit
        +----> event-write request ----> event recorder / async FIFO

lifecycle + fault supervisor supplies `ready` and owns safe teardown
```

Design rules:

- one sequential owner per state register;
- explicit `valid/ready/started/completed` transaction signals;
- index, transition counter, event, and pulse direction commit from the same
  accepted decision;
- no derived “busy gap” between request and pulse ownership;
- policy calculation is side-effect-free and independently testable;
- lifecycle and fault state can prevent a new acceptance without corrupting an
  already accepted atomic command;
- v8 checks `consumer_ready` while ARMING, not on every `ST_ACTIVE` decision,
  and
  production ties the input high. Preserve that contract for lockstep; any live
  readiness gate is a separately qualified behavioral change;
- preserve v8's configuration-stability contract. The current pulse path reads
  cooldown at acceptance, pulse-high at launch, pulse-low at phase transition,
  and blanking while busy; software keeps configuration stable throughout
  ownership. Formalize that assumption and preserve live sampling, or treat
  latching configuration into a command as a behavioral successor;
- all saturating counters, limits, and reset semantics are named; and
- unused release protections are either connected and tested or removed from
  the public design contract. Production currently ties `consumer_ready` high
  and does not exercise the core's software-index checking ports.

Replace stale-latch booleans with an explicit episode state, for example:

```text
CLEAR_AVAILABLE
    -- accepted SMALL_ADC_INHIBIT clear --> CLEAR_CONSUMED_WAIT_LARGE

CLEAR_CONSUMED_WAIT_LARGE
    -- accepted ordinary large decrease --> CLEAR_REARM_DWELL
    -- repeated conflict/minimum ---------> fail closed

CLEAR_REARM_DWELL
    -- another large decrease ------------> restart dwell
    -- full fresh neutral dwell ----------> CLEAR_AVAILABLE
```

V8 consumes the stale-clear budget on decision acceptance, not pulse
completion. Preserve that rule for lockstep. The pulse engine may have a
separate command-outstanding state, but it must not defer episode-budget
consumption.

### B2. Refactor in behavior-preserving slices

Use one narrow pull request per step. Each step passes B0 lockstep plus the full
PR suite before the next begins.

1. Add named aliases and a cycle-equivalent `decision_accept` boundary without
   moving or centralizing the behaviorally significant nonblocking assignments.
2. Extract detector synchronizing/debounce/conditioning.
3. Extract the delivered-sample power-window timebase.
4. Extract the pulse engine and introduce explicit transaction handshakes.
5. Extract the pure priority decoder returning decision data only.
6. Replace stale-latch flags/counters with the explicit episode FSM.
7. Only after the acceptance boundary is lockstep/formally proven, centralize
   duplicated index/event/counter side effects on decision acceptance.
8. Extract lifecycle and sticky-fault supervision.
9. Extract event formatting and FIFO ownership.
10. Simplify the AXI wrapper after all core interfaces are stable.
11. Either honor AXI `WSTRB` byte strobes or explicitly reject unsupported
    partial writes and test the response.
12. Remove dead diagnostics and obsolete integration documents only after the
    generated documentation and tests cover their replacement.

After each slice compare:

- public cycle behavior and stored traces;
- accepted decisions, pulse waveform/width, committed indexes, event bytes,
  counters, lifecycle/fault transitions, and quiescence;
- synthesis utilization and inferred BRAM/DSP;
- OOC timing/CDC/DRC/methodology; and
- integrated reports whenever hierarchy or constraints change.

### B3. Generate ABI and configuration definitions from one schema

Create one reviewed machine-readable specification, for example
`spec/tandem_agc_abi.yaml` or SystemRDL, covering:

- register offsets, access types, reset values, fields, widths, and enums;
- the 140-bit configuration bundle and 30-bit status bundle ordering;
- controller states, fault flags, decision reasons, and feature flags;
- 104-byte session request layout and validation ranges;
- metadata extension and 16-byte gain-event layout;
- default timing/threshold values and units; and
- schema/ABI compatibility rules.

A deterministic generator should produce:

- Verilog include/package constants and pack/unpack slices;
- Linux C headers/constants used by `adi_tandem_agc.c` and UAPI code;
- Python constants/`struct` definitions used by `metadata_abi.py` and validators;
- Markdown register/layout tables; and
- cross-language golden byte vectors.

Commit generated outputs for review, stamp them with the schema hash, and add a
`--check` mode that fails CI when regeneration changes the tree. Keep behavioral
validation hand-written; the same schema must not be both the only encoder and
the only oracle.

Gate: changing a field in only Verilog, C, Python, or documentation becomes
impossible without a generated-file or golden-vector failure.

### B4. Expand formal verification

Retain Icarus simulation and extend the B0 bounded formal reference job using
SymbiYosys or a supported commercial engine after every refactor slice. Prove
at least:

- no command acceptance unless the internal RTL state is `ST_ACTIVE` (the
  public metadata state is `ARMED_AUTO`), the live request is AUTO, and there is
  no fault, blanking, cooldown, or outstanding command; lifecycle state—not a
  live `consumer_ready` sample—is the v8 readiness prerequisite;
- withdrawing AUTO prevents a new acceptance on that edge;
- every accepted decision causes exactly one paired index step, one matching
  event-write request, and one complete paired pulse in the same direction;
- when the FIFO has space, each event-write request stores one record; when it
  is full, the accepted pulse/index step follows v8 behavior while exactly one
  dropped write produces visible overflow and sticky fault evidence;
- outside ARMING/fault-clear index seeding, index/counter/event-write motion
  requires acceptance; later pulse waveform edges may only belong to a prior
  acceptance, and FIFO pops remain an independent read-side transaction;
- RX1/RX2 command bits and recorded indexes remain paired;
- indexes never wrap or cross configured limits;
- pulse high/low widths meet the configured minimum;
- faults are sticky until a permitted clear and cannot erase an active command;
- ownership is not released while a command is outstanding;
- at most one stale-latch clear occurs per episode;
- re-arm requires the specified later large decrease and fresh neutral dwell;
- HOLD/fault reaches quiescence within a bounded interval;
- FIFO order is preserved, records are neither duplicated nor silently lost,
  and overflow is visible;
- configuration snapshots cross coherently and exactly once; and
- lifecycle transitions remain within the allowed graph.

Use explicit environment assumptions for running clocks, no intervening reset,
legal bounded/stable configuration, detector stability, and the v8
configuration/consumer contract when proving completion or bounded quiescence.
Prove safe abort/reset behavior separately when reset is allowed. Use a
single-clock core harness and separate multi-clock logical protocol harnesses;
formal can prove handshake/FIFO logic under its clock model, not metastability,
placement, physical bus skew, or constraint correctness. Require cover traces
for acquire, increase, ordinary decrease, stale-latch clear, re-arm, HOLD during
a command, fault, FIFO wrap, and recovery. Formal evidence complements Vivado
CDC/timing analysis, simulation, routing, and hardware; it does not replace
them.

### B5. Modernize CDC deliberately

First write a domain/crossing inventory naming every source clock, destination
clock, reset, data stability contract, synchronizer, handshake, FIFO, timing
exception, and matching test/property.

Evaluate AMD XPM primitives one crossing at a time:

- `xpm_cdc_single` for independent stable bits;
- `xpm_cdc_handshake` for coherent configuration/status snapshots;
- `xpm_fifo_async` for event transport; and
- `xpm_cdc_async_rst` for reset assertion/release.

Do not mechanically replace the custom CDC library. The OOC XDC currently uses
`set_clock_groups -asynchronous`, while integrated constraints intentionally
use bidirectional `set_max_delay -datapath_only` so stable data/gray buses retain
physical bounds. A broad asynchronous clock group can take precedence over
useful internal timing constraints. Redesign constraints and primitives as one
reviewed change, then require:

- reset-order, clock-phase, stopped/late-clock, and multiple-ratio simulation;
- formal handshake/no-loss/no-duplication properties;
- `report_cdc`, timing-exception, and bus-skew review;
- routed OOC and full integrated implementation; and
- targeted hardware acquire/release/FIFO stress.

References:

- [AMD Xilinx Parameterized Macros](https://docs.amd.com/r/2022.2-English/ug953-vivado-7series-libraries/Xilinx-Parameterized-Macros)
- [AMD Vivado design constraints methodology](https://docs.amd.com/r/2024.2-English/ug949-vivado-design-methodology/Constraining-the-Design-Correctly)
- [AMD Vivado CDC analysis](https://docs.amd.com/r/en-US/ug906-vivado-design-analysis/Running-Report-Clock-Domain-Crossings)

### B6. Simplify OOC and release evidence tooling

Define the threat model before adding more artifact-hardening code:

- accidental stale/partial/wrong-source evidence;
- corruption or substitution after a process boundary;
- untrusted pull-request code on a shared runner; and/or
- a hostile same-user process on the build host.

For the first two, use private temporary directories, no-follow/regular-file
checks, bounded reads, atomic publication, content hashes, immutable CI
artifacts, and provenance attestations. Never run untrusted PR code on the
trusted runner. If a hostile same-user process is truly in scope, process/user
isolation and a locked ephemeral runner are the primary controls; an ever more
complex report parser is not a sufficient security boundary.

Split the OOC flow into:

1. a Vivado runner that creates raw reports and the routed DCP;
2. a small extractor that emits versioned canonical `metrics.json` from raw
   reports;
3. a policy validator that checks structured timing/CDC/DRC/methodology,
   provenance, source hashes, and an explicit waiver inventory; and
4. an artifact publisher that atomically emits checksums and scoped status.

Keep raw reports for human review. Prefer stable rule IDs and structured values
over exact prose occurrence counts, while pinning the parser to the qualified
Vivado version. Mutation tests should independently alter every metric, missing
file, duplicate record, path, hash, version, waiver, and publication state.

Apply the same pattern to final release verification. Extend the current
17-field asset verifier with a hash-bound evidence index linking source lock,
manifest, Actions supporting-metadata record, routed reports, exact bundle/DFU, four deployment
receipts, hardware reports, local and remote tag object/target records, the
exact live/committed/indexed binary-verifier bytes, and published asset. Record
the index digest in an independent immutable location; a self-hash alone does
not prevent replacing both the index and its members.

### B7. Refactor the hardware harness around pure boundaries

Preserve all current safety gates while separating:

- immutable campaign planning/configuration;
- one serial-scoped `RadioSession` that alone owns device mutation and cleanup;
- acquisition and raw evidence capture;
- pure signal/metadata analyzers;
- pure release-policy validators;
- versioned report schemas and atomic persistence; and
- aggregate/index hashing, external digest anchoring, and archival.

Centralize repeated release constants in the generated schema or a single
versioned policy module, then retain independent assertions for security- and
physics-critical values. Add replay tests that feed captured detector,
metadata, IQ-summary, transport-gap, and cleanup traces through the same pure
validators without hardware.

Complement the current regex source-order guards with executable kernel tests:
extract a host-testable transaction/lifecycle helper or add KUnit tests for
prepare, arm, verify, release, restore failure, ownership conflicts, and
stale-latch clearing. Keep the cheap source guards as an early warning, not the
only proof.

### B8. Provide one developer entry point

Add `make check-tandem` backed by a small repository script. It must invoke the
same commands and test selection as PR CI, not a drifting approximation.

Suggested layers:

```text
make check-tandem-fast    syntax, generated files, lint, elaboration, focused tests
make check-tandem         complete offline PR suite and all tandem RTL simulations
make check-tandem-ooc     clean-commit routed Vivado OOC, explicit trusted host
make check-tandem-build   full source-locked Pluto build/package, trusted host
make check-tandem-hw      plan/dispatch guarded hardware phases, explicit operator
```

Print tool versions, deterministic seeds, selected manifest, and artifact paths
at the start. Fail on missing required tools; do not silently skip a release
gate.

## 6. Testing standard

### 6.1 Testing pyramid

The table below is the RC10 requirement using capabilities that exist now or are
explicit P0 deliverables in A1. Post-v8 generated-file and formal checks become
mandatory only when B3/B4 land; they do not retroactively block v8.

| Tier | Trigger | Required coverage | Authoritative result |
|---|---|---|---|
| Edit/commit | Every change | syntax/lint available for changed files, compile/elaboration, focused Python tests, deterministic RTL unit simulation | Local log tied to diff/commit |
| Pull request | Every PR | complete offline Python suite, all tandem RTL suites and existing stress seeds, source graph, existing ABI oracles, kernel guards | GitHub-hosted required checks |
| FPGA OOC | Candidate and CDC/RTL/constraint changes | clean-commit synth/place/route, timing, utilization, CDC/clock interaction, DRC, methodology, DCP | Hashed `ooc_pass_nonauthorizing` evidence |
| Integrated build | Every candidate/final build | exact manifest, complete Pluto route, packaged identities, artifact checksums, optional supporting provenance | Trusted runner artifact and reports |
| One-radio hardware | Behavioral, structural RTL, CDC, constraint, or physical pulse-path change | focused lifecycle/fault/transport/safety cases and pulse timing; optional stale-latch observer diagnostics | Serial/artifact-bound receipts and reports |
| Four-radio candidate | Every release candidate | full three-band steady/transient/modulated matrix, policy sweeps, lifecycle, soak, teardown | Hash-bound campaign index with digest recorded in promotion review |
| Final identity | Final v8 build | full four-radio candidate matrix; reduced confirmation remains unavailable until a guarded runner exists | Final qualification index |
| Persistent rollout | Published release only | cold-boot identity, safety, RX/tandem smoke, rollback readiness | Per-radio install receipt |

After B3/B4/B6, edit/PR gates additionally require clean ABI regeneration,
cross-language goldens, parameterized seeds, the formal safety subset, and
canonical structured OOC/evidence validation.

### 6.2 Test design rules

- A test should assert external behavior or deliberately named architectural
  transactions, not incidental internal register names.
- Every regression gets a red-before-fix test at the lowest useful layer and a
  higher-layer test when the defect crossed a boundary.
- Randomized tests use explicit seeds and bounds; failures print enough state to
  reproduce the exact sequence.
- Independent oracles must not derive expected bytes solely from the code under
  test.
- Hardware settling is observation-based, not a sleep-based assertion.
- Negative tests cover malformed input, stale/missing artifacts, cleanup
  failures, clock/reset ordering, partial writes, process death, and resumption.
- A test report is valid only after the owning device/session has closed and
  durable cleanup has been re-read and validated.
- Simulation models cite hardware documentation or captured measurements and
  are tested before serving as design oracles.

## 7. Development workflow

For each change:

1. State the affected contract and whether the change is behavioral,
   structural, evidence-only, or documentation-only.
2. Identify which existing evidence becomes stale.
3. Add or select the failing/relevant tests before implementation.
4. Make the smallest coherent change with one owner per state update.
5. Run the lowest tiers locally, then the complete PR-equivalent suite.
6. Review generated diffs, CDC/constraint changes, failure cleanup, and report
   schema changes explicitly.
7. Commit only a clean, reproducible state; record deterministic seeds and
   artifact locations in the PR.
8. Advance to OOC/integrated/hardware tiers according to the affected boundary.
9. Update this plan, design docs, release notes, and manifests when a gate or
   contract changes.

Pull requests should be narrow. Do not combine RTL behavior, CDC primitives,
constraints, ABI changes, hardware-policy thresholds, and evidence-parser
rewrites in one review unit.

## 8. Evidence and retention standard

The following is the implemented minimum Track-A candidate archive. A6 captures
`actions-run.json` and `attestation-verification.json`, and the trusted package
provides the payload/report members. `scripts/tandem_release_evidence.py`
creates the immutable candidate and campaign indexes, detached SHA-256 files,
and cross-links; it validates but does not invent operator review/signoff or
waiver records. The final archive follows the same pattern with
`final-artifact-index.json`, `final-qualification-index.json`, and
`published-release-index.json`. Existing OOC, package, lifecycle, and campaign
outputs are preserved under their real names rather than renamed:

```text
tandem-agc-v8-rc10/
  candidate-index-input.json
  candidate-index.json
  candidate-index.json.sha256
  campaign-index.json
  campaign-index.json.sha256
  source/
    tandem-agc-v8-rc10-source.yaml
  evidence/
    source-lock.txt
    source-and-tool-hashes.txt
    evidence-sha256.txt
    ooc-status.txt
    tandem-agc-v8-integrated-waivers.json
    ... every other exact REQUIRED_EVIDENCE_ROLES member ...
  ooc/
    exact-ooc-directory/
      status.txt
      timing-metrics.txt
      evidence-sha256.txt
      cdc-summary.rpt
      cdc-details.rpt
      clock_interaction.rpt
      ... all other files in the strict OOC inventory ...
    status.txt.sha256
  integrated/
    exact-extracted-bundle/
      SHA256SUMS
      PAYLOAD_SHA256SUMS
      packed-VERSIONS.txt
      system_top_timing_summary_routed.rpt
      system_top_route_status.rpt
      system_top_drc_routed.rpt
      system_top_methodology_drc_routed.rpt
      system_top_cdc_routed.rpt
      system_top_bus_skew_routed.rpt
      system_top_utilization_routed.rpt
      ... provenance, payloads, and original logs ...
  artifact/
    actions-run.json
    attestation-verification.json
    exact-bundle-name.tar.gz
    exact-bundle-name.tar.gz.sha256
  hardware/
    deploy/SERIAL/ram-boot-receipt.json
    lifecycle/SERIAL/muted-metadata-batch-lifecycle-v5.json
    stale-latch/SERIAL/stale-latch-report.json  # optional BLOCKED diagnostic raw member
    full/SERIAL/release-hardware-report.json
    soak/SERIAL/release-hardware-report.json
  review/
    promotion-signoff.json  # operator-owned; not synthesized by the verifier
```

For the final artifact, the canonical archived source path is
`source/tandem-agc-v8-source.yaml`, and the same descriptor shape is stored as
`final-index-input.json`. The final root additionally retains
`lineage/rc10/{candidate-index,campaign-index,...their complete members...}`,
`candidate-to-final-diff.json`, `final-artifact-index.json`,
`final-qualification-policy.json`, `final-qualification-index.json`, the exact
four-radio selected final evidence, local annotated-tag record,
`github-remote-tag-record.json`, published DFU/FRM and bundle, release manifest,
the indexed `scripts/verify_release.sh`, verifier-result wrapper (including the
same verifier SHA-256), and
`published-release-index.json`, with every index's detached `.sha256` sidecar.

`actions-run.json` is the exact normalized `gh api` result shown in A6,
including repository, workflow path, ref/event, head SHA, run ID/attempt,
status, conclusion, and URL. `attestation-verification.json` records the exact
`gh attestation verify --format json` argv, subject/bundle digest, workflow/run
predicate, exit status, and the actual nested tool output when verification was
performed; otherwise it has the exact not-performed shape shown in A6. The
index uses relative paths, records schema versions and SHA-256 for every
file—including raw transient/IQ sidecars—and preserves each tool's original
directory tree.

`candidate-index-input.json` and `final-index-input.json` use the exact
top-level shape `{schema, schema_version, stage, release, source, build,
artifact, harness, evidence}` consumed by the A6 command. `release` has exactly
`firmware_version`, `kernel_version`, `hardware_model`, `metadata_abi`, and
`tandem_agc`; `source` has `commit` and the canonical `manifest_path`; `build`
has integer `run_id` and `run_attempt`; `artifact` has `dfu_path` and integer
`fit_bytes`; `harness.paths` is exactly the sorted
`ARTIFACT_HARNESS_PATHS` constant, including both
`scripts/tandem_release_evidence.py` and `scripts/verify_release.sh`; and
`evidence.members` contains exactly one
`{role,path}` for each sorted `REQUIRED_EVIDENCE_ROLES` entry. The
planted-success `_fixture()` in `tests/test_tandem_release_evidence.py` is the
executable descriptor template and the offline gate keeps it contract-equal.

The archive may live in immutable release storage rather than Git. Its trust
root is not its self-hash: record `candidate-index.json.sha256` and
`campaign-index.json.sha256` in the independent promotion signoff, and record
the final published-index digest in independent immutable release-hosting
metadata and the release notes—not inside an input that the index itself
hashes. GitHub provenance attestation is optional supporting evidence under the
single-owner/operator trust model. Archive everything before the 90-day Actions retention expires.
Preserve failed evidence under a distinct attempt identity; never edit it into a
pass.

## 9. Risk register

| Risk | Consequence | Control |
|---|---|---|
| Broad refactor mixed into RC10 | Release evidence reset and schedule expansion | Retain RC9 firmware and deterministic packaging; change only the guarded route/authentication boundary and receipt v3, and defer architecture work until after v8 |
| RC4 evidence reused | Unqualified post-RC4 RTL ships | New source lock, route, artifact, and four-radio campaign |
| Wrong version baked into image | Fleet audit reports previous release | Explicit `RELEASE_VERSION`; package-time exact check; read packed `/opt/VERSIONS` |
| Workflow branch falls through to wrong manifest | Trusted build uses unrelated source graph | Test allowlist, manifest, and package prefix as one mapping |
| Same version string on different bytes | Hardware report accepts wrong image | Bind deployment receipt and DFU/FIT hashes to every report |
| Ambiguous DFU target | Wrong radio rebooted or modified | Exact-serial/topology deployer; refuse multiple/unresolved targets |
| Duplicate device IP follows the wrong `/24` route | SSH reads or reboot target another serial | Refuse a pre-existing exact route; acquire, verify, refresh, and finally remove one selected-interface `192.168.2.1/32` lease |
| Factory password leaks or authentication silently changes | Credential exposure or unauditable transport | Private mode-0600 password file; `sshpass -f`; fixed one-prompt SSH policy; never print/hash/archive password bytes; revalidate before every SSH call |
| `-R`/`-e` semantics misunderstood | Candidate boots QSPI and produces false evidence | Forbid `-R`; exact `-e` command planner; new boot-ID/version and unchanged-QSPI proof |
| Candidate written persistently | Recovery and provenance risk | RAM-only tooling; forbid boot/env/full ZIP/raw MTD |
| OOC pass treated as firmware pass | Integration timing/CDC/fit defect escapes | Scoped verdict and mandatory full Pluto route |
| Integrated reports only copied, not checked | DRC/methodology/routing issue ships | Structured fail-closed integrated policy and reviewed waivers |
| Hand-packed ABI drifts | RTL/kernel/Python disagree silently | Single schema, generated outputs, independent golden vectors |
| Implicit request/pulse gap | Lost/duplicate physical gain step | Explicit handshake, atomic commit, lockstep and formal proof |
| CDC primitive swap breaks constraints | Metastability or unconstrained path | Crossing inventory; primitive+constraint change together; route/hardware gates |
| Hardware fixture variance | False regression or false pass | Measured attenuation, serial-scoped baselines, multi-radio/band coverage |
| Cleanup failure hidden by earlier error | Radio remains transmitting or owned | Independent best-effort teardown and durable post-close validation |
| Evidence parser becomes an oversized acceptance boundary | Complexity and false confidence | Single-owner threat model; producer-shaped reports; exact local hashes; optional supporting attestation only |
| Actions evidence expires | Release cannot be audited later | Immutable campaign archive and published hashes before 90 days |

## 10. Suggested issue breakdown and order

### Must complete for RC10/v8

- **P0-1 — RC9 build/index complete; RC10 route/auth correction implemented.**
  RC9 proved full fit, route, timing, integrated validation, deterministic
  packaging, and candidate indexing. Its first live execute stopped before
  reboot or DFU because competing `/24` routes selected the wrong serial and
  the factory password-only image rejected key-only SSH. RC10 preserves
  firmware and package behavior while adding exact temporary `/32` isolation,
  private password-file SSH, verified route cleanup, receipt v3, and new
  lineage. Every build gate must now replay on the RC10 commit.
- **P0-2 — Completed before RC10: generalize candidate lineage.** Muted lifecycle
  qualification consumes validated manifest/receipt inputs instead of RC4/R18
  constants; RC10 updates the exact identity fixtures.
- **P0-3 — Completed on RC6; mandatory replay on RC10: lock deterministic shared-dwell/stale-latch RTL proof.**
  Keep the re-arm,
  one-pulse-per-episode, bounded-clear, HOLD, and failure cases mandatory at
  both supported clock ratios. Add direct increase/conflict/re-arm class-change
  regressions proving no dwell credit transfers. Retain the BLOCKED hardware
  observer only as an optional diagnostic.
- **P0-4 — Route/auth receipt v3 implemented; live use pending: exact-serial RAM deployer.**
  The deployer authorizes no `-R` or persistent-write path. Execution and the
  immutable v3 receipt remain bound to the selected serial, exact `-e` command,
  candidate bytes, new boot identity, unchanged persistent-flash digest,
  verified safe state, exact host-route lease, and verified route release.
- **P0-5 — Implemented; qualification pending: prepare the RC10 source graph and trusted route.** Add the RC10
  manifest, source-graph checks, immutable version name, tested workflow
  allowlist, manifest mapping, package prefix, fail-closed integrated report
  policy, release-wide evidence verifier, and executable final-identity
  confirmation gate.
- **P0-6 — Freeze and qualify the exact source.** Run the complete offline suite
  and clean routed OOC, then create/protect the RC10 firmware source lock without
  changing the commit.
- **P0-7 — Build and route exact bytes.** Exercise route, timing, unconstrained
  paths, CDC, skew, DRC, methodology, utilization, warning, and DCP gates.
- **P0-8 — Verify and index exact bytes.** Verify candidate artifact, packed
  identities, checksums, the exact supporting-metadata record (the default is
  `attestation-not-performed`), and the offline evidence index. Optional GitHub
  provenance cannot gate the build.
- **P0-9 — Execute four-radio RAM campaign.** Full phases, targeted lifecycle,
  separate soak, cleanup, and durable campaign index.
- **P0-10 — Final identity and publication.** Merge exact source, final build,
  required final qualification, annotated tag, exact asset, immutable manifest,
  and verifier.

Dependencies are linear from P0-1 through P0-10, except P0-2/P0-3/P0-4 can be
developed in parallel before P0-5/P0-6. Any behavioral fix restarts the chain at
P0-1 with a new candidate identity.

### First post-v8 hardening increment

- **P1-1 — Unified `make check-tandem`.** Match CI exactly and add generated,
  syntax, lint, and deterministic-seed checks.
- **P1-2 — Stable observation/lockstep boundary.** Preserve v8 behavior without
  tests naming internal implementation registers.
- **P1-3 — ABI schema generator.** Generate Verilog/C/Python/docs/goldens and
  enforce clean regeneration.
- **P1-4 — Formal safety harness.** Prove acceptance/pulse/index/event,
  stale-latch, lifecycle, fault, FIFO, and CDC invariants.
- **P1-5 — RTL transaction decomposition.** Extract conditioner, timebase, pulse
  engine, pure policy, episode FSM, supervisor, and event recorder in order.
- **P1-6 — Hardware trace replay.** Validate the scalar model and policy against
  real detector/metadata traces.
- **P1-7 — OOC/evidence split.** Separate runner, extractor, structured policy,
  and publisher; add release-wide evidence verification.
- **P1-8 — Hardware harness decomposition.** Separate session ownership,
  acquisition, pure validation, schemas, and aggregation.
- **P1-9 — Guarded fault-injection campaign.** Add planted-oracle and hardware
  phases for host death, cable/device loss, ENSM disturbance, watchdog/iiOD
  restart, deliberate FIFO pressure, recovery, and re-attestation.

### Later improvements

- **P2-1 — CDC/XPM evaluation.** Crossing inventory and one-at-a-time migration
  with constraint redesign.
- **P2-2 — Executable kernel lifecycle tests.** KUnit or host-testable transaction
  state machine alongside source guards.
- **P2-3 — Persistent fleet deployment tooling.** Canary/batch install receipts,
  cold-boot verification, and tested rollback.
- **P2-4 — Reusable trusted candidate workflow.** Replace growing branch-specific
  conditionals with a protected, manifest-driven workflow that remains
  impossible for untrusted PR code to invoke.

## 11. Definition of done

### Tandem AGC v8 release

The release is complete only when all of the following are true:

- the exact source is clean, reviewed, committed, and protected by a new RC10
  source lock;
- offline, RTL, source-graph, kernel, and candidate-specific harness gates pass;
- fresh OOC and full integrated Pluto implementations pass their correctly
  scoped gates;
- there are no failing timing endpoints, unconstrained release paths, CDC-10
  paths, critical warnings, unknown rules, or unreviewed DRC/methodology waivers;
- artifact sidecars, inner checksums, the exact supporting-attestation record
  (including the accepted not-performed form), DFU/FIT structure,
  `device-fw`, and all packed component identities are exact;
- the same DFU bytes are RAM-booted with valid receipts on all four radios;
- stale-small-ADC recovery passes the deterministic RTL gate at both supported
  clock ratios, including one-clear, paired-index, suppression, recurrence,
  minimum-index, and re-arm properties;
- muted lifecycle, metadata transport, steady quality, transient response,
  modulated quality, policy sweeps, repeatability, required offline fault cases,
  teardown, and cleanup all pass on the required radio/band matrix;
- every handled exit leaves TX muted, DDS disabled, selectors at ZERO, tandem
  released, and FIFO/fault/overflow state acceptable and explained; any
  uncatchable interruption is nonauthorizing until the separate recovery gate
  passes;
- the final build's machine-readable candidate-to-final diff is reviewed and
  any functional change resets the candidate;
- the final exact bytes pass the full four-radio campaign;
- the local annotated tag object and the retained canonical-remote tag/peel
  record agree and target the qualified final commit, and the immutable manifest
  describes the published bytes;
- `scripts/verify_release.sh manifests/tandem-agc-v8.yaml` passes against the
  published asset with the mandatory DFU-suffix dependency, and the recorded
  verifier digest equals its indexed, live, and qualified-commit bytes;
- the published-stage invocation of `scripts/tandem_release_evidence.py verify`
  with `--index` set to
  `/absolute/evidence/tandem-agc-v8-final/published-release-index.json` passes
  and binds the source, supporting-attestation record, routed evidence, candidate/campaign/final
  parent indexes, deployment receipts, four-radio reports, both tag records,
  exact binary verifier, and publication;
  and
- `RELEASE_NOTES.md` and operator/build/test documentation record the final
  identity, evidence, installation, rollback, and known limitations.

### Post-v8 refactor

The refactor is complete only when:

- public ABI and v8 golden behavior remain unchanged unless a deliberately
  versioned successor is introduced;
- decision, pulse, index, event, lifecycle, fault, and FIFO transactions have
  explicit ownership and formal properties;
- configuration/register/event definitions are generated consistently across
  Verilog, C, Python, documentation, and golden vectors;
- tests use stable architectural observations and protected-reference lockstep;
- CDC primitives and constraints have a reviewed crossing inventory and routed
  proof;
- one developer command matches PR CI;
- OOC and release validation use structured, scoped evidence with a documented
  threat model; and
- routed utilization/timing and targeted hardware behavior meet or improve the
  v8 baseline without weakening safety or cleanup.

## 12. External technical references

- [AD9361 Reference Manual UG-570](https://www.analog.com/media/en/technical-documentation/user-guides/AD9361_Reference_Manual_UG-570.pdf)
- [AMD Vivado Implementation UG904](https://docs.amd.com/r/2022.2-English/ug904-vivado-implementation)
- [AMD Vivado Design Analysis and Closure UG906](https://docs.amd.com/r/2022.2-English/ug906-vivado-design-analysis/Using-Report-DRC)
- [AMD Vivado Logic Simulation UG900](https://docs.amd.com/r/2022.2-English/ug900-vivado-logic-simulation)
- [SymbiYosys documentation](https://yosyshq.readthedocs.io/_/downloads/sby/en/latest/pdf/)
