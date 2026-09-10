# C1 plus ROM read-ahead: frozen actual preparation

The additive bank/joiner harness preserves the accepted C1 numerical, fault,
ownership, latency and qualified-status observation contracts. **147 offline
tests pass**; the parent independently repeated 147 tests. This report packages
preparation, not an actual FFT or physical result. One separately authorized
K1/M1 vendor evaluation is running on original handle23845; its terminal result
will be reported separately. No synthesis, route or production integration is
authorized by this package.

Tested FW `e7d8b229e1719eb4fd40810b4e5be5fad98a96d6`, HDL
`54af5727801b3f0cb3a9a178b3135cc6e5a311fd`. The additive ROM itself remains
the separately tested `32b20cb750caeede27561193728f088bc249195e` source.
All seven canonical runtime files are byte-identical to the accepted C1
freeze: no schema migration or replacement of canonical control is needed.

## Bounded source and observation changes

New additive bank and joiner modules differ from their complete canonical C1
bodies only by module substitution, two default-off parameter declarations,
fail-closed 0/1 checks and forwarding. Strict whole-file inverses restore the
old source bytes. `PRIVATE_ROM_READ_AHEAD` (K) and
`PRIVATE_BLOCK_METADATA_READ_AHEAD` (M) reach the additive ROM explicitly.
The word and metadata recurrences add no cycle, arithmetic or ownership rule;
their combined logical cost at D18 is +107 register bits and 105 mux bits
before optimization. Mapped resources, power and timing remain unmeasured.

The new preparer admits only a complete passing C1 source/run, including its
pinned 48-entry inventory
`9c81c43d9ed0bbc6cfba1d40074d11ec8cd94530fc9d7920de809bd6d68ce39c`.
Every inherited entry is checked against that immutable inventory. The old top
and runner are restored in memory before hashing; original settings/metadata
are preserved separately. Rehashing a modified old fault observer, reference,
helper, vector, inventory or metadata does not admit it. All seven runtime
hashes, exact source membership, new helper/observer and additive ROM bindings
are checked independently. Missing/duplicate/wrong/X/Z options and existing or
symlinked output paths fail closed.

The top changes only the candidate module/options and adds a ROM observer and
terminal receipt. The independent dec20 R1/D0/S0 reference is unchanged. The
runner has a literal inverse to C1, explicit option readback and sanitized
Python preflight before project creation. Every old stimulus, fatal,
current-fault fence, qualified-status predicate, numerical and full CSV gate
remains literal. No vendor core is added for the new ROM subtree shadow.

That shadow is the literal C1 ROM with matching D18, balanced comparison and
S1 parameters, fed solely from the actual ROM's nine input ports. It compares
all old coefficient, metadata, control and state observations unconditionally,
including invalid cycles. There is no invalid coefficient mask. Direct
four-state concatenations are evaluated in the inactive region before NBA and
again after NBA at +1ps, draining same-time active port propagation; the
observer does not drive or delay the DUT. Positive terminal coverage requires
acceptance, first/last slots, stalls, reset, current/final fault edges and
private-core-reset samples. These counters count sampled edges, not distinct
fault/reset episodes.

The pre-existing whole-bank status policy is explicitly different from the
historical raw217 observer: all 216 other fields remain unconditional; all
eight status bits are compared whenever either valid is not exactly zero.
Invalid-only raw status differences must be separately logged/accounted.
Neither this package nor an eventual qualified pass is a raw217 pass.

## Executed offline evidence

- V1 `/tmp/starlink-rom-actual-prep-v1.5XwNZEFU`, original17052: exit0,
  76 passed in3.50s, two pytest iterator warnings. This retained draft lacked
  the final inherited-inventory binding and allowed zero private-reset samples;
  it is not the admitted actual preparation.
- V2 `/tmp/starlink-rom-actual-prep-v2.ho7jRY8n`, original91849: exit0,
  **147 passed in19.28s**, Ruff clean. Includes 87 new tests and the unchanged
  60-test word/metadata scope. Full old-source restoration, rehashed inherited
  mutations and positive private-reset receipt checks close the draft gaps.
- Parent repeat original95792: exit0, **147 passed in19.28s** at
  `/tmp/starlink-rom-actual-parent.ZzUfJJnV`.

All four K/M combinations elaborate the actual hierarchy using a stub without
executing it. Separate executed joiner/ROM fixtures prove the observer,
unconditional invalid/state views, raw-input aliasing, reset/stall/current-fault
sampling and semantic mutation rejection; they explicitly do **not** claim a
vendor FFT or actual bank lifecycle. The complete actual C1 suite supplies that
separate runtime scope only after its authorized run reaches terminal.

## Exact freeze and one-shot invocation

Prepared `/tmp/starlink-rom-prefetch.j829ht/rom-actual-prepared-v1` contains
56 inventoried members plus SHA256SUMS. Settings are R/D/S/C/K/M=111111,
EXACT_EXTRA_EPOCHS=1, FAST_MHZ=175, QUICK=0.

- Inventory SHA256
  `6f5eddb99510e869bbe65548acc6ed64cd76bd98908aacfcd6e1c0361ccbe4ae`.
- Runner `9f198abf60d9119eae2ef565ae3d65b64104f93ce5f1b5be4b2e89776dd3deed`.
- Preparer `bca85ff4affb7fd4650489103ee5750567fe031d225fda057303007defb840b3`.
- Observer `de1dc6d2590014ed80351038077c2af52ba71ce7d200c704169f8243ab2ae45a`.

The already-launched one-shot command is
`bash /tmp/starlink-rom-prefetch.j829ht/rom-actual-owner-v1/owner.sh`.
Owner SHA256 is
`ab2237e268c40a56ffcd050c4ecd47ba3b0989e5240812059a8fa13b532e57c1`;
original handle23845 started at `2026-09-10T12:25:25.886262245Z`.
It invokes Vivado2022.2 with explicit SuSE LD_LIBRARY_PATH, two threads, and
unique log/journal arguments before tclargs. It rejects reused paths and
retains process exit separately from source/IP and independent receipt checks,
including on tool failure. No retry is permitted. An independent terminal
check additionally requires the exact manifest hash and identical owner
before.sha256/after.sha256. Generated IP is absent before project creation and
hashed afterward; that is not a precompile IP equality claim.

Both main CSVs must retain SHA256
`25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122`
(589950 lines each); both extra CSVs must retain
`b965d12603a64111fa9c6ea36cb0f12189945ad4d9be7cf4fbd883980c4ec4a0`
(33180 lines each). The new frozen verifier independently requires the old C1
receipts, qualified-status accounting and unconditional ROM receipt. No fixed
invalid-only status count is assumed.

## Portable offline package

`reports/experiments/20260910-rom-actual-preparation-v1.tgz` contains 3794
artifact/source members plus its embedded receipt. SHA256
`d5288cabd35cfb9da0d142f6c93d248c174c3427354b76823f6e411ff43b1e8d`,
12,572,643 bytes. The companion JSON hashes every inner file. It includes both
attempts, changed-source snapshots, generated benches/executables/logs, all
dependencies and the exact prepared freeze, but not the running actual project.

The first collector attempt rejected two deliberate symlink-rejection fixture
artifacts before creating the archive. Original attempts and symlinks remain
intact locally. Packaging-only copies omit those exact two links, record each
path/target and the failed attempt in `final/symlink-exclusions.json`, and retain
all regular target data. The unchanged collector separately records redundant
pytest-current links. No test, runtime, gate or actual source was changed for
archival. Git-object and inner-member verification accompany publication.
