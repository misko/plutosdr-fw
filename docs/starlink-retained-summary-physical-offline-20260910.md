# Offered-summary physical recipe: offline and unbound

Historical scope: this report records the unbound source `0f2714d60`. The later
accepted-actual binding is documented separately in
`starlink-retained-summary-physical-binding-20260910.md`; the original observations
and unbound-source references below are preserved.

This is additive preparation code only. No offered-summary actual evaluation is
accepted by this source, no real physical input bundle was copied, and no vendor
tool was launched. `admission.py` deliberately has `ACCEPTED_ACTUAL = None` and
an invalid, visibly `UNBOUND_PENDING_ACCEPTED_SUMMARY_ACTUAL` manifest identity.
The generated Tcl independently rejects that unbound identity before creating
an output directory. Root retains exclusive authority over future vendor runs.

## Sources and unchanged physical contract

All additions are in the existing bank-arithmetic firmware worktree, not the
retained candidate's source tree. Its HDL pin remains
`b26f56dd32106c8e91290d075255ac4a6b9ff72d`. The four offered-summary RTL files
are immutable reference copies under `tools/retained_summary_synthesis/reference/runtime`;
their full hashes and the twelve unchanged runtime hashes are in `source_pins.json`.

The previous source-specific helper `81d418d1…` and synthesis Tcl `767ecdfb…`
are retained verbatim. `derive.py` records **13 helper and 9 Tcl literal edit
groups**, checks occurrence counts and reconstructs both entire original files.
The implementation only selects the four summary paths, adds
`INPUT_OFFER_FAULT_SUMMARY=1`, binds the future summary actual CLI, updates artifact
names, and adds the explicit original-actual admission gate/reference bookkeeping.

Unchanged settings: sixteen runtime files, R1/B1/O1/L1, private descriptor offer
1, closed-input option 1, one generated FFT, `xc7z010clg400-1`, source 100 MHz and
island 175 MHz, Vivado 2022.2, two threads, rebuilt hierarchy,
`AreaOptimized_high`, OOC, and control-set threshold 4. No timing exception or
latency/numerical tolerance is added. The unchanged recipe still records all
clock directions, setup/hold, unconstrained paths, CDC, exceptions, source/IP/DCP
hashes and post-failure integrity. Tool completion is not timing qualification.

Pinned unchanged assets:

- Clock XDC: `bac30eff84cc71d1f273104b716b388b55e51d33be10f9beaf1901232193ba3f`.
- Two-thread Tcl: `aec974f2800f01285e888d1b188cd089534941922531914926a8e1b568d4c227`.
- FFT factory: `0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d`.
- Diagnostic route Tcl: `034d1eaa197757b762644acd0cad9dc267338ae23fd5d757290c8485d0f1ac9a`.

The prior synthesis and route owners are reference files only; this preparation
does not run, rewrite, or authorize them. A future source-specific owner must be
reviewed against the accepted actual and prepared inventory before execution.

## Hard future actual gate

Before any real copying, a later reviewed source change must bind one exact
original owner/run, manifest, owner/command/outcome receipts, full results and
frozen summary CLI. The gate checks original and executed source manifests,
all sixteen runtime bytes, terminal exit/no timeout/no interruption, source
checks, result-collector exit, actual generated FFT bytes, and unique successful
automation marker. It preserves the original full numerical/service result
bytes; it does not reconstruct or substitute a passing result for a failure.

Then the frozen actual CLI must pass `verify --live` and `results`, with complete
JSON equality to the pinned original result, **before output creation**. A later
source check is also required before producing the prepared inventory. Missing,
failed, stale, wrong-source or merely offline-script results cannot satisfy the
current unbound real entrypoint. Actual manifest/owner binding is deliberately
pending; mocks do not provide it.

## Retained offline results

Exact command scope:

```text
env -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH -u PYTHONOPTIMIZE \
 /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest -q \
 tests/test_starlink_retained_summary_synthesis.py \
 --basetemp=<unique recovery directory>/cases \
 --junitxml=<same directory>/results.xml
```

Final original tool receipt `7f80e4`, exit 0: **60 passed in 0.78 s**.
Artifacts are in
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-summary-physical-offline-v3.AYQexGzb`.
Its source-before tar matches the live tested source after the run (`tar -d`, exit 0).

Every positive synthetic admission/CLI/Tcl fixture is named and marked
`MOCK_ONLY`: receipt/byte checks are exercised with test-local monkeypatches,
and the Tcl stops at an explicit `create_project` error. No real actual collector,
physical preparation, generated IP, synthesis or route is exercised by these mocks.
Tests cover the unbound real gate, complete source/owner/result/IP rejection,
both whole inverses and mutations, exact options/readback, sanitized children
with unchanged parent environment, non-overwrite/lexical paths, unchanged
constraints/runtime selection, and post-failure copied source/clock integrity.

Prior attempts remain intact: v1 `u9eEozRe` had 45 passes/3 failures because the
synthetic kernel filename lacked the slash required by the unchanged selector;
none reached the vendor trap. Corrected fixture v2 `hhFvYRul` passed 59 tests.
The final additional case rejects altered actual generated-wrapper bytes while
the synthetic owner receipt remains unchanged. No original failure was erased.

Final important SHA-256 values:

- Copier: `26a4e81835ca8504873e85699645e73b193e2c3e4fd5e5573a9fa18925a3858b`.
- Admission: `127b35f80d81a236f7b21b4d2b1c711f910f2dadd8bb2cfcd7ccaf16e15cee9b`.
- Derived Tcl: `b2ba1d114a457d3fa6c161e6cb9126885445c91256592ee237273289c09cac70`.
- Policy tests: `854b8e0987b2f7f3d9cccc9636c25ce5907f66aff3e17921735a809075d127bf`.

No physical timing/CDC closure, full receiver, continuous ingress, native-fine
concurrency, IIO bandwidth, or radio/deployment conclusion follows from this gate.
