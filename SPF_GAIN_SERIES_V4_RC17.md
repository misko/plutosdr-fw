# Gain-series v4 RC17 candidate

Status: source candidate. Build and hardware promotion pending. RAM boot only
until the two-radio gates pass.

RC17 addresses the direct-IP control-plane lifecycle failures reproduced on
RC16 at 1--2 MS/s. RC16 moved correct, complete IQ frames but performed slow
IIO startup and teardown synchronously in the UDP control handler. Host retries
could then queue duplicate requests and stale responses.

## Source locks

| Component | Commit | Protected source tag |
| --- | --- | --- |
| Firmware parent | assigned by the RC17 parent commit | eventual RC tag |
| Buildroot | `564013d1dd32a0d64b4ab81d5e22d03757146bdf` | `gain-series-v4-rc17-source/buildroot-commit` |
| Direct IP gadget | `8814aec26c6920afd79e198227d4f192adf16518` | `gain-series-v4-rc17-source/ip-gadget-commit` |
| Common USB gadget | `2e8e40ade5dcf3c7880a5ebb58419ad7c37ed552` | `gain-series-v4-rc14-source/gadget` |

All other FPGA, kernel, and bootloader pins are unchanged from RC16. The
canonical source graph is `manifests/gain-series-v4-source.yaml`.

## Changes

- The control epoll thread launches and cancels protocol-v3 RX workers without
  polling or joining them in a request handler.
- Distinct startup, run, quit, and done eventfds prevent lifecycle signals from
  consuming each other.
- `STARTED` is sent only after worker initialization; capture is released only
  after that response is accepted locally.
- `STOPPED` is sent only after worker cleanup and IIO ownership release.
- A bounded replay ring coalesces pending duplicates and byte-replays completed
  requests.
- Peer-scoped request high-water marks reject evicted stale requests.
- Stream generations and completed-stream tombstones prevent old worker and
  STOP events from affecting a newer stream.
- The host drains stale control responses within one receive window rather
  than consuming a new transmit attempt.

The detailed state machine is in the direct-IP source at
`SPF_IP_RX_LIFECYCLE.md`. SPF also carries the system-level design and hardware
test plan.

## Promotion gates

1. Source-graph verification and all 14 common USB plus four direct-IP native
   tests pass in CI.
2. Build artifact hashes and attestation verify after a fresh download.
3. RAM boot succeeds on two independently identified Pluto+ radios.
4. Ten consecutive parallel finite captures pass at each of 1, 1.25, 1.5, 2,
   2.5, and 3 MS/s with no control failure, sequence discontinuity, partial
   frame, UDP reassembly error, or leaked owner.
5. The high-rate ladder, direct USB regression, standard IIO configuration,
   and attenuated TX2-to-RX1/RX2 loopback pass.
6. Gadget restarts and repeated START/STOP cycles recover cleanly.

Only after these gates pass may the source commit be tagged, published as a
GitHub prerelease, or considered for persistent QSPI promotion.

## Known follow-ups

The daemon does not yet have a wall-clock cleanup watchdog or a wire-level
lifecycle telemetry query. If kernel teardown hangs indefinitely, the service
supervisor remains the recovery boundary. RC17 deliberately does not return
`STOPPED` early or reuse uncertain DMA ownership.
