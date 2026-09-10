# Primary replay: native capture, coarse FFT and independent pilot

The single independent primary175MHz replay passes on FW `aea211988` /
HDL `8e2d11a8fabcfea58e28d1b469c93cdc43f5fd24`. Only additive test/oracle/
runner/evidence files were integrated. All receiver RTL remains byte-identical
to `9759cf121e899975e841b17c593289cf646249fa`; no radio, PPU, receiver profile
or main branch changed.

## Actual execution and limits

Original root session75766 completed exit0 at2026-09-10 04:52:07 UTC in
`/tmp/starlink-bank-route.I50MDJ/main-bank-native-paired-520-175-v1`.
The explicit520 profile uses a real15MHz continuous-valid sample clock,
100MHz native/coarse processing and the actual generated175MHz FFT model.
Injection is disabled; native coefficients, command and result lifecycle use
public AXI. This remains a static arithmetic/ownership control, not causal
acquisition, synthetic PSS lock, deployed clocks, ADC/DMA/IIO or RF evidence.

The original strict gates pass:

- 130exact native capture words; one26-word packet, read twice (52public words),
  retained across coarse stop and explicitly released with checked telemetry.
- 894exact coarse scores,447map words,512pilot words/2048bytes; pilot delivery
  and indexed support continue through the independent coarse stop.
- 319fast-clock capture/FFT overlap observations and842 native-compute/
  coarse-active/pilot-DDC input accept observations. The latter are canonical
  input beats, not2.5MS/s output words or proof of all detector stages computing.
- Actual source admission at8589934602, capture start8589935064,461samples of
  lead; first/last capture116835.433/125435.433ns and first FFT input123615.592ns.
- Native winner-17, Re144077802, Im-27795799, Ex204670264, Eh1073742825.
  Normalized score approximately0.0979737, not the injected PSS at offset447.
- Existing deliberate late invalid-release fault remains classified as failed
  joint coarse health; retained coordinates and already-recorded pilot bytes
  survive. This is not the broader concurrent reset/gap/expiry suite.

The simulator ends at311240ns. Its short fixed-clock execution does not prove
sustained60MS/s receiver service, worst-case admission lead, timing accuracy or
physical timing closure. No detector-control timing variant is included here.

## Independent source and oracle checks

Root first checked the alternative archive SHA256 and182 successful-run
artifact hashes:86frozen files per clock plus five log/scope/pilot/generated-IP
artifacts per clock. All389 archive members have unique safe paths. The
historical source/failed447attempts remain unchanged in that archive.

This new primary replay closes the separately documented project-local Python
freeze gap for this execution:97frozen files include all ten deterministic
runtime modules and their encoded-path manifest before project creation.
The runner rechecks the exact frozen inventory/hashes after simulation.
Root independently matched every runtime copy against current source.

Compared with the alternative's86files,83are byte-identical. Exactly three
existing files differ: the subsequently hardened runner and policy test, plus
the independent pilot receipt's generator_sha256 field. Root initially expected
only two differences; inspection found this third provenance-only field.
The original primary pilot fixture came from an earlier generator-file revision;
all source, metadata, coefficients, score and pilot payload bytes are unchanged.
Root independently regenerated the pilot files from the actual replay source
using today's generator: all five payload files byte-match, and again only the
generator_sha256 receipt field differs. No tolerance or fixture was changed.

The native oracle was independently regenerated before execution at
`/tmp/starlink-bank-route.I50MDJ/main-bank-native-oracle-520-v1`; its receipt
SHA256 remains `a269658050d852c55fc0a2128a8eb7ccca5f4abc494a7f8cf306311c70551383`.
The exact input native arithmetic/ranking was independently checked with Python
integer/Fraction calculations during parent review, not taken from RTL output.

Root policy regression:201passed in6.67s across
`tests/test_starlink_bank_native_paired.py`,
`tests/test_starlink_paired_realtime_psma_stop_policy.py` and
`tests/test_starlink_realtime_probe_result.py`. The initial invocation mistakenly
named a nonexistent helper-policy file and collected zero tests; the corrected
selection above is the201-pass result, not a relabeled failed RTL test.

## Preserved evidence

Archive `20260910-bank-native-paired-primary-replay.tgz` includes all97frozen
files, scope, raw compile/elaboration/simulation logs, generated FFT wrapper,
actual pilot binary, outer transcript/journal and201-test JUnit receipt.
Vivado2022.2 and installed simulation libraries remain external dependencies.

| Artifact | SHA256 |
| --- | --- |
| Primary archive | `3b070b550a66c52ca3c2ac36d485b390584cf7217fa2fd9dcde742d8077ed0c5` |
| Actual simulation log | `2baba07d0f72290ab65b74bfeae31a68be5ac6ed82aeba15a919832ab7cfdb08` |
| Scope | `6a3d12dde6064713a20b5c3c5c28e47b5af071ca302003d25e9490b6e452c082` |
| Policy JUnit | `0c3067028d1737bc84553c12e76030aeb51538d9e5e1a5ce244f7368a683db16` |
| Actual pilot bytes | `9ca24563bda3a3df6a0f780f3eb976eaac044d97ce752277b3781ba95942d1bd` |

## Next authorized stage

Implement/offline-test a NEW true-PSS fixture at offset520, with a distinct
request/coefficient/fixture identity. Preserve original447/520controls. Replace
only numeric samples[520,586), leaving the old447PSS ending at512 and1000control
unchanged. Independently regenerate all three18-bit Cmodel FFT stages,
exponents,1341scores,447x2map,512pilot words and native61-lag/full26word oracle.
Require input-derived winner0/Re=Ex=Eh1073742825/Im0; never use RTL as the oracle.
Full source/support/lead and new fixture hashes must be reviewed before actual
175/200 execution. No actual or physical trial is authorized for this new
fixture yet. Expired/late commands, common source gaps, FFT-only reset/vendor
faults and independent lane/joint failed receipts remain next reviewed cases.
True-PSS concurrency still will not establish causal acquisition or RF lock.

Keep the entire scanner objective: native15/30/60fine, canonical15coarse,
independent2.5MS/s IIO evidence, eight120ms-valid visits over300s, complete
physical qualification and .18 canary before .17 PPU Ethernet deployment.
