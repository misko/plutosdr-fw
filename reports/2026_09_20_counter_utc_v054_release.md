# Pluto+ v0.54 counter-UTC RC1 release record

The published prerelease [`v0.54-plutoplus-spf-counter-utc-v1-rc1`](https://github.com/misko/plutosdr-fw/releases/tag/v0.54-plutoplus-spf-counter-utc-v1-rc1) adds the UTC counter observation provider to the v0.53 adaptive-scan-v2 firmware baseline. It preserves v0.53 manual-gain operation, the repeated-target fast path, and paired-RX capture. The exact release artifact passed the integrated route, package verification, and two-radio functional and persistent-candidate gates.

## Exact build and sources

- Trusted workflow run: [35536057445](https://github.com/misko/plutosdr-fw/actions/runs/35536057445), attempt 1.
- Firmware source: `0ffdfe964247c63945aa6d0e4a159ee09f241396`.
- Buildroot: `0c53efafd58b59dc74c60007d977c67198e5f32e`.
- Linux: `9be23c72ebf3d0237c9a10e141c682a2d227ee17`.
- HDL: `145bd47e55d5c5537e0ba49d53cb25a5393f66ba`; HDL quantulum: `364b3dc7e770c3971d1f41a75c00e6cae76e2e6d`.
- libiio 0.25: `e234d2d7fae19d47e4655068df69679c3b2f4427`; U-Boot Xilinx: `1ff0468e9bea29b0a768a7bf52db8d025c521b9a`.
- Metadata: `3294365ff44da26b261be4a2ccb241b7896d23ad`; USB gadget: `1bbe9f0ee4a70374964804de09b7503da260b059`; IP gadget: `b066059e54817ad9a140c3549fcee0bf39dadc81`.
- Companion PPU: `5d7962f64bb30ba28ce6e57eee39a06e74aacc47`; tracker: `12822ed7f2b64b32d4c8a47108ce90c2c088b328`.
- Integrated route verdict: PASS; routed WNS 0.767 ns and WHS 0.019 ns.

The published DFU is `plutoplus-spf-counter-utc-v1-rc1-0ffdfe964247-pluto.dfu`, SHA-256 `3611adb9d38d5db9e6e94453a195194022dd7c7ba0ca649234f783d1bb016ada` (12,784,195 bytes). Its FIT body is 12,784,179 bytes, SHA-256 `8d5a8ee4e75d34dffb7e55fee084afd5771a4bbcbe4ed54414b04ccb69ff65f6`. The matching FRM SHA-256 is `7c2d64060e682c7a5d81a076fffdeaf049eb7206542f63da6ac4f89513d44307`; the packaged and persistent iiOD SHA-256 is `c932714528a168c88222593e1e678c93983ae707b12ec5fb0d0d7cbc519888f2`. The release includes the source/build manifests, provenance, original build checksum lists, capture replay validator, and checksummed hardware evidence archive.

Publication verification downloaded all 24 release assets and confirmed byte-for-byte identity with the locally tested package; the outer and inner evidence checksums passed. The tag resolves to firmware source `0ffdfe964247c63945aa6d0e4a159ee09f241396`. The latest stable release remains v0.53.

## Two-radio acceptance

Both local radios passed 300-second single-RX captures at 10, 15, and 20 MS/s and a 300-second paired-RX capture at 2.5 MS/s with RX mask 3. R18 (`1040007c4a94000211000b009186843ef2`) delivered 6,647 single-RX visits and all 2,220 paired-RX visits. R15 (`104000b29905000e17000800065934759d`) delivered 6,654 single-RX visits and all 2,217 paired-RX visits. There were no skipped, invalid, cancelled, or DMA-reported missing samples. Counter continuity, IQ geometry, timing-query, and anchor-coverage checks passed for every accepted capture.

The largest query interval across the accepted matrix was 29.163 ms, below the 50 ms gate. The largest inclusive timing-anchor span was 5.080 s, below the 10 s gate. These are counter observation and coverage results; they do not establish absolute UTC accuracy.

Both radios then passed 10-second post-persistent single-RX 10 MS/s and paired-RX 2.5 MS/s smoke captures. Their anchor streams matched their new persistent boot UUIDs. One successful persistent receipt per radio attests the exact FIT/FRM, protected-region checks, return identity, and TX-safe state. The CRC-valid U-Boot environment comparison on each radio found only the expected `fit_size` change to 12,784,179; no gain or other radio-setting changes were found. Persistent checks followed software reboots, not physical power cycles.

## Qualification limits

`utc_hardware_qualified` remains **false**. No independent UTC-timed RF reference was used, so this release makes no absolute UTC error or ±100 ms claim. Counter coherence and low query latency cannot substitute for RF-reference calibration.

The accepted paired-RX captures are functional evidence; the tracker importer does not support paired-RX input. Full-IQ import remains on the older v0.52 contract and has not been validated for this v0.54 release. This campaign retained capture summaries, visit metadata, and timing anchors rather than archived full-IQ payloads. No physical power-cycle qualification was performed.

Raw hardware reports, accepted summaries, environment comparisons, persistent receipts, and the replay validator are in the release asset `hardware-captures.tar.gz` and companion release files. The archive excludes credentials and private flash backups.
