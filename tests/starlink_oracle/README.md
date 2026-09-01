# Starlink synchronization golden oracle

This is a pure NumPy, test-only numerical oracle for the experimental
RX-only firmware branch. It is not firmware, a decoder, a deployment tool, or
evidence of a received Starlink signal.

## Provenance

Sequence authority is the clean worktree
`leo-tracker-reduxredux-pss-sss-five-dwell` at
`12317cd1ba03c540d1797f7a17f16312b6510612`. The reviewed source is
`src/leo/analysis/starlink/templates.py`, file SHA-256
`3fc955bfd19907d74ebf6bf2691ec9a7af075260bfb6be727992eb7dcfccc199`.
It cites the UT Radionavigation Lab simulator revision
`5de898badd03f6a8b3c7d5196b9b31d4039263ed`; the reviewed `genPss.m` SHA-256
is `1d091f2ca957fa01dec5ffc067f7867cc879345785b0f88db515265dcea7e494`,
and `sssVec.mat` SHA-256 is
`d1e35826279baf0fc3e5a6fa3d34e5a83dd525956132ad9cecdb2af48450f982`.

Projection authority is the tracked
`leo-tracker-reduxredux-all-rate-main/src/leo/analysis/starlink/pss_timing.py`
introduced by commit `f49d66926a6cc0232cc5e9513c44cc6cca768d34`, file SHA-256
`aa022ef819cd25e89156c09ddd3478693d61d7c6ac9fd99a8510f61c9c763513`.

The native PSS digest is
`e950ec78f60f8d9d9f0f6d98fc9f17ae77ebed9ef224df38efe9545c8d5a21f7`.
SSS uses natural 1024-bin order, `sqrt(1024) * ifft(X)`, and a normal
32-sample cyclic prefix; only PSS has an inverted prefix. Its frequency-vector
and native-symbol complex64 digests are
`1ece2fb4719619d004fbb2524f6db70f2a3972e85ac5919799fc792c11012452`
and `21e9844ec67a498b139e914d0123cb5cdd35a53b1c7b6388115c483220c8e5be`.

FFT and projector byte hashes were derived with NumPy 2.5.2 and independently
reproduced by this branch with NumPy 2.4.6. They are implementation
fingerprints in addition to the sequence authority, not a claim that every FFT
library must emit identical low bits.

## Boundaries

- Rates are exactly 15, 30, and 60 MS/s.
- The float search is direct lag/CFO correlation with explicit tie-breaking.
- The fixed model is CI16 with Q1.15 coefficients and saturating 48-bit
  accumulators. It contains no NCO; inputs are zero-CFO or pre-corrected.
- No real 30 or 60 MS/s validation capture was found. Tests at those rates are
  synthetic. Real-capture replay is deliberately outside this first slice.
