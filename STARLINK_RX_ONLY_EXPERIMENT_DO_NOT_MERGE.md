# STOP: STARLINK RX-ONLY EXPERIMENT — DO NOT MERGE OR DEPLOY

This document applies to branch `codex/starlink-rx-only-do-not-merge`.

The branch is an isolated, receive-only numerical experiment. It is not a
firmware release candidate and must not be merged to `main`, tagged as a
release, built for a release manifest, or deployed to any PlutoSDR/Pluto+
hardware.

The first permitted slice contains only the pure NumPy golden oracle in
`tests/starlink_oracle`: exact published PSS/SSS construction, declared
15/30/60 MS/s geometry, deterministic edge projection and direct float search,
and an explicitly specified fixed-point correlation model. It does not modify
HDL, Linux, Buildroot, boot artifacts, device configuration, transmit paths, or
Git submodules.

Evidence limits are equally strict:

- 15 MS/s has an identified real RX1 replay elsewhere, but real-capture replay
  is not imported into this first slice.
- 30 and 60 MS/s vectors in this slice are synthetic only; no real validation
  capture was found.
- A correlation match is synchronization evidence, not payload decode,
  spacecraft identity, transmission authority, or deployment qualification.

Any expansion beyond this oracle requires explicit coordination and a new,
reviewed scope. In particular, do not add an NCO, HDL DUT, firmware integration,
hardware capture, device access, or deployment step on the authority of this
branch document.
