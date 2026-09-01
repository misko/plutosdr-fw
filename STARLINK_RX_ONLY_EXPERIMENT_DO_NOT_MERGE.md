# STOP: STARLINK RX-ONLY EXPERIMENT — DO NOT MERGE OR DEPLOY

This document applies to branch `codex/starlink-rx-only-do-not-merge`.

The branch is an isolated, receive-only FPGA experiment. It is not a firmware
release candidate and must not be merged to `main`, tagged as a release, or
persistently flashed to any PlutoSDR/Pluto+ hardware. Any hardware trial must
be a receipt-backed, guarded RAM boot on the one explicitly selected radio,
with automatic return to its known persistent image after power-cycle.

The permitted development scope is defined by
`STARLINK_PSS_15_30_60_PLAN.md`. It includes the pure NumPy golden oracle,
standalone detector RTL and simulation, an RX-only/1R1T FPGA shell, Linux nodes
that match that shell, out-of-context and full Vivado measurements, and then
strictly gated 15, 30, and 60 MS/s RAM-only trials. The shell removes the FPGA
TX datapath; it does not claim the physical RFIC has ceased to be a transceiver.

Evidence limits are equally strict:

- 15 MS/s has an identified real RX1 replay elsewhere, but real-capture replay
  is not imported into this first slice.
- 30 and 60 MS/s vectors in this slice are synthetic only; no real validation
  capture was found.
- A correlation match is synchronization evidence, not payload decode,
  spacecraft identity, transmission authority, or deployment qualification.

The branch name, this stop document, and every artifact label must retain the
words `DO NOT MERGE`. A passing detector test, Vivado build, or RAM trial does
not authorize QSPI/SD persistence, unattended RF operation, release promotion,
or a merge into firmware `main`.
