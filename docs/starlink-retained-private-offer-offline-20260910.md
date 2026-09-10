# Private descriptor offer: isolated offline candidate

Source freeze FW `19c1436f3e8d1a84a6e35381a86e8ea7f6e904cc` /
HDL `75fa090855e872ec1fd56877af218a5900882429`. Three additive RTL copies in
`retained_output_candidate`; original qualified runtime, actual bundle, old
helpers and shadows remain unchanged. Literal per-file inverses restore their
complete qualified hashes. The opt-in changes only a private descriptor load:
the top supplies raw offer/phase separately from unchanged qualified admission.
No extra FF or cycle is declared; there is no physical timing result.

Every accepted edge must have a known asserted offer and identical descriptor.
Inactive rejected offers may update invalid descriptor/output-metadata bits,
checked against an independent model; they cannot acquire ownership. Active,
parked, sticky-faulted and ACK-clearing descriptors hold. The original 23 healthy,
37 rejected and 12 reset stimuli run in both default and enabled modes. All old
outputs/state remain compared except those two explicitly modeled invalid fields
in the enabled unit test. Whole healthy compositions retain literal old shadows.

Owner original 67829: **32 PASS / 7.19 s**. Independent parent original 49914:
**32 PASS / 7.22 s**, all 40 source pins unchanged. Targeted controls include
missing/wrong-phase offers, X/Z offers both outside and on accepted edges, and
wrong sampled descriptors. A standalone caller accepting with missing/X/Z offer
violates the tested interface premise; the witness rejects it, not the RTL itself.
Earlier 26 PASS / 4.89 s remains retained. Its source26 reconstruction is labeled
post-run, not a pre-run receipt, and matches all 13 original generated benches.

Replay: `python -B -m pytest tests/test_starlink_retained_control_candidate.py -q
-p no:cacheprovider --basetemp=<unique-non-tmp-directory>/cases`.
Raw roots: `retained-private-offer-tests-v1.xZ6zD8rp`,
`retained-private-offer-tests-v2.07be9IZT`, and `retained-private-parent.PmtrTqnC`
under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

Compact archive `artifacts/retained-private-offer-v1.tar.gz`: SHA256
`df4c538339e870d1d5ab13d4c19364debcec61e2539e84b7cb11cdbb998dc39d`,
383,844 bytes; 267 safe regular members / 266 hash-and-length receipts. Includes
parent full source snapshot, all three attempts' logs/XML/generated benches,
and full regular-file inventory; compiled vvp payloads remain in place and pytest
symlink aliases are listed, not archived. Collector checks are separate from32.

Published only on the existing DNM branch, HDL first. No actual FFT, clock change,
radio or production gitlink change. The separate closed-input candidate has not
yet been evaluated and is not part of this source freeze or result.
