# Single-receiver FPGA GLRT firmware goal

User-authorized on 2026-09-08. This is a NEW independent Astra agent at xhigh,
forked from the FPGA agent's branch. It does not replace the existing paired
PSS/host-GLRT task.

## Exact user request

"launch a new astra xhigh agent to fork from the fpga agents branch, and set a
goal to implement only GLRT single receiver firmware. GLRT should run at
2.5/5/10/25/60 MSs and return host side 2.5MSs IQ stream for host side glrt
validation. no PSS"

## Create the persistent goal immediately

Call create_goal with the objective below, without a token budget. This request
explicitly authorizes a persistent goal in YOUR task. Do not create a goal in
the coordinator's or original FPGA task. Check get_goal first if resuming.

Implement and qualify single-receiver, receive-only Starlink pilot GLRT FPGA
firmware at source rates 2.5, 5, 10, 25, and 60 MS/s, with no PSS detector in the
active FPGA design, exporting a continuous counter-attested 2.5 MS/s complex IQ
stream for independent host-side GLRT validation of the same observations.
Complete the source, firmware/HDL/kernel/host integration, all five rate builds,
appropriate numerical and transport validation, and coordinated hardware
qualification. Demonstrate live FPGA GLRT evidence agreeing with independent
host GLRT where the exported bandwidth makes the comparison observable. Report
false positives, missed/ambiguous observations, timing/CFO uncertainty, and rate
limitations honestly. A plan, arithmetic simulation, or host-only detector does
not complete the goal.

## Starting point and isolation

- Work only in `/home/mouse9911/gits/plutosdr-fw-starlink-glrt-only` and isolated
  component checkouts created for this task.
- New branch: `codex/starlink-glrt-only-do-not-merge`.
- Exact fork commit: `7e20f6e5c693e8aa1a92b2dd3f918feffff722ad` from
  `codex/starlink-rx-only-do-not-merge`.
- Pinned HDL: `edb0f7070ac4fe01a9a08f9d7d98bc70d03114d4`.
- Pinned Linux: `5d706586c591d4c9f5fc8a308b2b248693c0d279`.
- The source worktree is `/home/mouse9911/gits/plutosdr-fw-starlink-rx-only`.
  It is an active agent's workspace: read-only reference, never edit it or
  check out another branch inside its components. Its untracked scratch files
  were intentionally not copied.
- Initialize this worktree's pinned component sources in independent working
  directories. Local Git objects may be reused, but no writable source/build
  symlinks into another agent's working tree. Use separate build/artifact roots.
- Keep firmware and component changes on new experimental do-not-merge branches;
  commit tested checkpoints and preserve source identities. Do not merge or
  deploy over production firmware as a shortcut.
- Read applicable AGENTS.md instructions. The older `FPGA_scanner_300s.md` is
  useful background, but its PSS preservation and 15/30/60 rate requirements are
  superseded for THIS task by the user request above.

## Architecture and validation requirements

1. Implement GLRT detection in FPGA. ARM/Linux may control the receiver and
   transport results/IQ, but do not silently substitute ARM or host-only GLRT.
   Establish an implementable numerical specification and resource budget first.
2. Remove both coarse PSS acquisition and fine PSS tracking from this profile's
   active netlist. Shared generic filtering, counters, FIFOs, buses and DMA may
   be reused without retaining PSS computation or PSS-trigger dependencies.
3. Support exactly 2.5/5/10/25/60 MS/s receiver modes. Verify actual hardware
   clocks, bandwidth and rate-specific GLRT behavior; do not substitute 30 for
   25 or claim a native-rate detector merely because the ADC accepts that rate.
   Rate-specific firmware builds are acceptable initially; document runtime
   versus compile-time selection. Prove throughput and bounded buffering at
   each rate, with meaningful latency and FPGA timing margin.
4. Export one continuous 2.5 MS/s CI16 stream from the SAME receiver observation,
   including observations without FPGA detections. Required source/output ratios
   are 1, 2, 4, 10 and 24. Design appropriate anti-alias filtering, frequency
   translation, gain/scaling and reset/transient handling for each mode. At
   2.5 MS/s, use the appropriate unity-rate path. The IIO output rate must be
   truthful; no full-rate continuous IQ-to-host shortcut.
5. Retain source/output counters, epoch/visit identities, frequency references,
   filter/group-delay mapping, clipping/overflow/gap evidence, and explicit
   invalid spans. No silent sample dropping or fabricated throughput. Output
   payload is 10 MB/s before protocol overhead; measure real transport headroom.
6. Use independent host GLRT acquisition on exported IQ, not FPGA-seeded host
   confirmation masquerading as independent validation. Compare the same time
   support and observable frequency band. Native-rate and 2.5 MS/s estimators
   need not yield identical scores; define justified agreement tolerances and
   explicitly account for information lost during filtering/decimation.
7. Validate against published/saved positives, noise and structured nonpilot
   controls, CFO/timing offsets, weak and short signals, and fresh held-out cases.
   Preserve a frozen numerical reference; use bit-exact RTL checks where suitable.
   Report real false-positive/false-negative evidence. Do not tune on holdouts
   and then report them as independent qualification.
8. Start with fixed-frequency single-receiver operation. Get GLRT plus IQ export
   fitting and routed at one rate, then complete the full five-rate ladder.
   Hopping is not required by this new request and should not delay this goal.
9. Close full-design placement/timing before hardware deployment. Exercise real
   IIO/DMA lifecycle, short and sustained capture, fault/recovery and restoration.
   Synthetic success is separate from live RF detector qualification.

## Useful inherited evidence and independent references

- Original FPGA checkpoint: 120 ms integrated replay exported exactly 300000
  supported samples with every IQ value matching the oracle and correct PPU
  coordinates; full paired-PSS receiver still failed placement. Removing PSS is
  the authorized architectural change for this new branch.
- Forked `tools/starlink_pilot_glrt_replay.py`,
  `tools/starlink_pilot_capture_dwell.py`, `tests/starlink_oracle/`,
  `hdl/library/axi_starlink_pilot_capture/`, and pilot DDC modules are useful.
- `/home/mouse9911/gits/pluto-plus-utils` has counter validation support on main
  at `b5e8f6f`. Reuse through a separate worktree if changes are needed.
- Scanner workspace `/home/mouse9911/gits/leo-tracker-arm-presence` contains
  `src/leo/analysis/standard/native_full_capture_glrt.py`,
  `native_glrt_fractional.py`, and `src/leo/scanner/native_presence/`.
  These are reference material, not an instruction to edit its active workspace
  or move its ARM implementation into the definition of FPGA GLRT. The scanner
  has independent holdout evidence and remaining short-burst limitations.

## Hardware coordination

The existing FPGA agent owns the experimental .18/.17 workflow. Coordinate
specific bench windows before any new hardware operation; do not interrupt an
active capture, build/deployment lifecycle or overwrite another agent's image.
Continue simulation/build/host work while hardware is unavailable.

- Original FPGA task: `01a05dc1-7a4b-71c1-9ae6-189b51bd83a1`.
- Coordinator task: `01a08195-4439-7fb0-8692-7e74693d867a`.
- Scanner task: `01a0628b-55fa-7813-8c0b-870c664f9320`.
- First canary .18: serial `1040007c4a94000211000b009186843ef2`, locally USB
  connected. Use exact-identity ownership and reversible RAM testing first.
- Outdoor .17: serial `104000bac4950008230026001b440a003a`, Ethernet-only,
  powered LNB/bias tee. Qualify .18 first, then coordinate .17 and use the known
  PPU deployment/rollback procedures when appropriate. Keep all TX muted.
- Do not use scanner .20/.21 or its currently selected USB spare .14, or
  smateway .15/.179. No new hardware purchase or physical rewiring is requested.
- User is away and cannot perform cable swaps. Do not block independent work
  waiting for physical changes. Ask at most one question at a time when needed.

## Progress reporting

Maintain this goal document and a concise milestone/evidence report in this
branch. Separate implemented/tested/synthesized/routed/hardware-qualified/live
validated status for each rate. Report resource use, throughput and remaining
issues. Send the coordinator your task id, confirmed model/effort, persistent
goal status, initial architecture, and any real external dependency. Continue
autonomously beyond checkpoints until the goal is achieved or a genuine blocker
requires input; do not stop merely because one implementation attempt fails.
