# Install and use v0.50 counter metadata

Verify the downloaded release assets against `SHA256SUMS` and the exact DFU/FIT identities in `counter-rx-v1.yaml`. Use the paired `.frm` for persistent updates and `.dfu` for the existing verified RAM-boot workflow. The release's PPU profiles bind installation to these exact bytes.

For physical AD9361 1R1T counter capture, keep the canonical AD9361 hardware identity and select mode `1r1t`, RX0, and manual gain. Use PPU's `AD9361_1R1T_TARGET_PROFILE` RX-layout expectation. Configure sample rate and analog bandwidth separately; 60 MS/s uses bandwidth no greater than 50 MHz.

Install the accompanying PPU revision and its native runtime:

```sh
scripts/install_native_libiio.sh --uv-bin /absolute/path/to/uv --metadata-abi 3 --counter-rx
```

Open `IioRadioDevice` with `expected_metadata_abi=3` and explicitly request `begin_metadata_capture(counter_only=True)`. The executable public-API qualification example is `scripts/issue97/public_capture.py` in the firmware source. It is restricted to the release qualification serial and is not a general fleet deployment script.

For the qualified finite high-rate profile, request 1,000,000 complex samples per frame and 50 kernel buffers, with a finite direct-async frame count. Verify that 50 buffers were actually allocated. Inspect every frame's `missing_samples_before`; a positive value is measured loss, not permission to treat the stream as contiguous.

Physical 1R1T does not support paired tandem metadata. For paired HOLD/AUTO, use physical 2R2T and omit `counter_only=True`.

## Exact installation profiles

Use `counter-rx-v1-1r1t-release-persistent-promotion` for a physical 1R1T radio,
or `counter-rx-v1-release-persistent-promotion` for physical 2R2T. The respective
RAM profiles are `counter-rx-v1-1r1t-release-ram` and `counter-rx-v1-release-ram`.
The profile must match the source and return topology. Use the existing PPU
`firmware flash-lan` or `firmware flash` command with that explicit profile;
its dry run produces the serial-bound plan and required execution phrase.

Matching PPU host release: [counter-rx-v1-host-v1](https://github.com/misko/pluto-plus-utils/releases/tag/counter-rx-v1-host-v1), source `d85199a5033e6cdf4ca735e24a440a9ea70d5329`.
