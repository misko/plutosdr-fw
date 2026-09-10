# Independent primary replay: generated clock under coarse traffic

The actual generated175 MMCM and unchanged complete bank-owned coarse pipeline
pass an independent primary-branch replay. This closes the finite active-reset
simulation test, not receiver clock/reset wiring or physical qualification.

Reviewed alternative pins: FW `704f58b2f161a5bb73f6ab2e64b3bc05f2f686f1`, HDL
`7d4d6d8cb482e60cf7ee557f2e86905d26155dd5`. Root read the complete bench, runner,
policy tests and report, and verified all124 JSON hash receipts. Only new
tests/evidence were merged. Tested primary pins: FW
`ad6dfbb79a93ad9d8bf882ef5672ef809cb2aaed`, HDL
`6ae9c302390b97f44d86f1d9e825a0cf40ae3464`.

One fresh actual-IP run at `/tmp/starlink-bank-route.I50MDJ/main-bank-clock-traffic-v1`
exited zero at02:55:46 UTC on2026-09-10. All32 frozen inputs byte-match the
alternative's final v3 snapshot. No receiver defaults, runtime RTL, arithmetic,
goldens, IP helpers or constraints changed. See the full contract and reset
witnesses in `../../docs/starlink-bank-clock-traffic-20260910.md`.

Results: five fresh healthy epochs each produce1,341 exact scores and1,536 exact
words at each transform boundary. Four failed epochs retain independently checked
score prefixes179/387/482/100. Total accepted counts are7,853 scores,
10,752 forward words,10,752 product words and9,985 inverse words. The unaccepted
held VALID score is also checked, not included in accepted totals. All five
generated-clock period observations and four reset/explicit-recovery cases pass.
The same-enabled detector remains quarantined through MMCM relock; enable-cycle
recovery starts a fresh source index. Earlier accepted prefixes are not relabeled
as healthy complete acquisitions. No input-clock-loss experiment was performed.

Portable root archive: `20260910-bank-clock-traffic-primary-replay.tgz`, containing
frozen local inputs, source/IP hash receipts, full Vivado log and simulation log;
no generated vendor RTL or project binaries.

```text
archive SHA256 a952fff8196a15247868d418ed4eb996274be9398668c4abfd8923bfb6a69de4
simulate SHA256 c06ca923d3ba1205f2d12d2f2aa7b60d1c836fc148bbf7267b1b8792d2f10cd5
```

Root's first unit command named nonexistent clock-test files and ran no tests;
the corrected clock suites pass90, and the subsequent clock/paired/map-lifecycle
selection passes279. The final expanded clock/paired/map/CDC/runner/soak/receipt
selection passes384 in3.27s; Ruff and diff checks pass. These host checks supplement
the real-IP terminal result.
The generated clock is still testbench-connected; arbitrary reset phase/width,
ownership-state sweeps, physical CDC/recovery/removal, source30/60 adapters,
production maps, pilot/native fine concurrency, receiver IIO/DMA and actual RF
remain separate requirements. No radio or PPU was accessed or changed.
