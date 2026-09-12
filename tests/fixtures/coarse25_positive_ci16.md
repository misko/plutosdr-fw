# Bounded recorded-IQ arithmetic fixture

`coarse25_positive_ci16.mem` contains the first 2048 complex CI16 samples from
the `positive_later_1` exported stream in
`reports/coarse25-temporal-validation-20260912/result.json`.

Words are `{signed Q[15:0], signed I[15:0]}`. Reconstructed little-endian CI16
bytes: 8192; SHA256
`fe50c3d29fd476d11049f3533c4aea703026080cf79a0156bbb3753c49c52db4`.

The stream is an offline frequency-corrected, filtered derivative of the
recorded 25 MS/s capture, beginning at the 36.62 s window. It is **not** a new
2.5 MS/s radio capture. Its pre-filter correction and exact source-index mapping
are in the linked temporal plan/receipt. Tests use it to check exact MAC and
normalization composition, not to establish a complete frame lock from this
short 0.8192 ms fixture.
