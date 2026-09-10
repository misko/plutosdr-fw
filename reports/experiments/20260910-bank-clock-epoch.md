# Separate 175 MHz candidate: actual generated clock and idle-bank reset test

The reusable `create_bank_owned_clock_ip.tcl` helper generates and validates a
dedicated Clocking Wizard 6.0 MMCM from an already buffered 100 MHz input. It
does not change `system_bd.tcl`, the PS FCLK1 output, or the AD9361 200 MHz
delay-reference connection. No receiver profile selects this helper yet.

The generated primitive identity is checked exactly: DIVCLK_DIVIDE=2,
CLKFBOUT_MULT_F=20.125, CLKOUT0_DIVIDE_F=5.750, CLKIN1_PERIOD=10.000 ns, one
MMCME2_ADV, two BUFGs (feedback/output), unbuffered input connection and
active-low reset mapping. The nominal ratio is 100 × 20.125 / 2 / 5.75 = 175 MHz.
This is generated-instance identity, not placed resource usage or clock timing.

## Executed simulation

`simulate_bank_owned_clock_epoch.tcl` uses both actual generated IPs: the MMCM
and unchanged FFT, together with the actual idle bank wrapper/reset synchronizers.
It connects the candidate bank FFT epoch reset to external reset AND manual
epoch reset AND MMCM LOCKED. No payload is presented.

Final v2 source: HDL `eaef91a6234d0ecf166933a460a486147287a32f`, firmware
`d78b9ecb9801ee4152319bded0a547a2764ca36b`. Vivado 2022.2 exited 0 at
2026-09-10 01:58:34 UTC with three healthy reset epochs and 3,072 measured
clock edges. In each epoch, 1,024 output periods average **5.714286133 ns**,
within the pre-frozen ±0.005 ns simulation-average gate around 1/175 MHz.
This tolerance is not a hardware jitter specification or STA uncertainty.

Executed boundaries:

1. Initial external reset release, MMCM lock and both real bank-domain reset
   synchronizers reaching healthy idle readiness.
2. Independent MMCM reset: observe its LOCKED drop, then require actual bank
   fast/slow reset fences, input readiness and output validity to be cleared
   within the test's 2 ps observation step; release and measure the next epoch.
3. Manual FPGA FFT epoch reset while MMCM remains locked: assert both bank
   fences, release/recover, and measure the third epoch.

The bench rejects a fast epoch opening without clock lock/reset release,
unexpected idle output/fault, missing epochs, wrong mean period and watchdog
expiry. The lock-drop stimulus is explicit MMCM reset, **not** a stopped input
clock; this does not qualify input-clock-loss detection. Healthy-ready markers
are sampled after a further eight fast clocks, not exact lock-latency measures.

The first v1 run also passed, but its diagnostic `time_ns=%t` used simulator
precision units rather than ns. V2 prints `$realtime` explicitly in ns and adds
the lock-prerequisite monitor; its three ready observations are 2870.713,
11600.713 and 17720.713 ns on the bench timeline. The original log is retained;
the period calculations were already in correct ns in both runs. An initial
Python policy fixture had a quoting syntax error; it was corrected before the
20 final admission/generated-contract/receipt tests passed with Ruff clean.

## Scope and reproduction

Run `simulate_bank_owned_clock_epoch.tcl NEW_OUTPUT` with Vivado 2022.2. Inputs,
helpers, bench and generated IP hashes are frozen before simulation. The helper
rejects reused IP and altered primitive identities; the runner refuses existing
output and rejects assertion/fatal text even with positive terminal markers.

Still unqualified: active-payload loss/recovery, the registered-scheduler variant,
receiver integration, MMCM placement/routing, generated clock constraints,
setup/hold/recovery/removal, CDC endpoint auditing, board I/O, RX calibration,
pilot/fine concurrency and RF. No radio, PPU source or firmware deployment changed.

Archive `20260910-bank-clock-epoch.tgz` retains v1/v2 runner/simulation logs,
scopes and frozen non-vendor inputs. Generated vendor IP and deployment binaries
are excluded and can be recreated using the frozen helpers.

- Archive SHA-256: `1a486980ad26e733aa74baa76d9851a37bb7646b4c2f9b9d1be1b7c889afcc86`.
- Final runner log SHA-256: `ac1ba8993cb30a39b00fb85eb8eaa2b5c9f4923bcc3d3166dfbe04c959d57c01`.
