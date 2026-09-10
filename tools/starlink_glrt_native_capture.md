# Native IQ diagnostic capture

`starlink_glrt_native_capture.py` collects one to three bounded GLN1 jobs over
Ethernet after an external owner has established the exact receiver, firmware,
60 MS/s calibration, RX configuration, TX mute and exclusive radio lease.
It does not change firmware or RF settings. Each complete job retains 79,200
CI16 samples (316,800 bytes) and its immutable 32-word arithmetic result.
Transport success still requires independent arithmetic replay and does not
qualify acquisition or physical precision.

The existing `--lead-samples` mode uses the kernel's source snapshot plus a
6,000–6,000,000 sample delay. Its persisted
`starlink-gln1-native-bringup/v1` protocol is unchanged.

## One predicted sample start

`--start-sample UNSIGNED_64_BIT_INDEX --jobs 1` selects the additive Linux
`native_capture_start_sample` attribute. The exact index is written after the
lead configuration, read back before enabling DMA, and checked against the
returned GLN1 result. Unsupported drivers or mismatched readback fail before
opening the buffer. A different returned start rejects the result while
retaining the received bytes and cleanup evidence. The request is single-use
in the driver, even if DMA or admission fails; there is no retry loop.

This mode publishes `starlink-gln1-native-exact-start/v1`, with the requested
index as a decimal string and both `acquisition_verified` and
`prediction_source_verified` false. These are diagnostic inputs supplied by
the caller, not evidence that the prediction came from a detected pilot.

Run `python3 -m tools.starlink_glrt_native_replay --capture CAPTURE_DIRECTORY
--bank BANK_FILE --output REPLAY_JSON` from the firmware repository to check
the saved original IQ against every reported integer moment. For exact-start
captures, replay also checks the requested decimal index against the returned
result and emits `starlink-gln1-native-exact-start-replay/v1`. Its
`exact_start_verified` flag establishes request/result correspondence;
acquisition, prediction-source and physical-precision flags remain false.
Legacy relative captures keep their existing replay schema.

Exact-start captures also retain `timing.json`, including failed attempts.
Its `starlink-gln1-native-host-timing/v1` milestones use decimal-string host
monotonic nanoseconds around context creation, verification, configuration,
buffer open, IQ/result arrival and cleanup. The owner can compare these with
coarse-stop milestones on the same host and boot. The buffer-open interval
includes network calls and radio DMA/admission work; it is not a timestamp of
the FPGA admission edge. The sidecar makes no source-continuity claim.

The finite GLF1 collector likewise writes `timing.json` using
`starlink-glrt-lean-host-timing/v1`. Its milestones distinguish receiving all
requested coarse IQ, buffer close, final snapshots, context close and final
attestation. The sidecar is included in the coarse summary's evidence hashes;
the existing complete-prefix and closure checks still apply. A diagnostic
owner should finish the finite segment before switching modes. Early close
can leave queued DMA data outside the saved file and fails those checks.

Do not use an idle GLS1 epoch as a continuity witness across GLR CLEAR.
The complete AXI/CDC simulation confirms that CLEAR resets `source_seen`,
invalidates a rebased idle scheduler epoch and sets its source fault even
with a continuous ADC, zero CDC/pacer drops and an advancing source counter.
Numeric coordinates remain useful, but an unchanged sample-index origin does
not by itself attest uninterrupted physical sampling across this boundary.

The kernel requires 6,000–6,000,000 samples of lead at its local post-DMA
snapshot, and rejects u64 end-of-pilot overflow. A request can become late
after that check; fault-free complete FPGA evidence remains required.
The caller must stop/drain the coarse GLF1 capture and all scheduled ownership
before switching the shared DMA to native IQ. There is no concurrent native
IQ tap and no additional FPGA resource requirement.

Qualification still requires a retained coarse prediction, radio/boot/RF
identity, source-counter continuity and measured handoff latency, followed by
matching the original IQ to the full-pilot fixed-point arithmetic. A physical
source interruption can invalidate a prediction even if its numeric sample
index is in range. No new accuracy claim follows from this interface alone.
