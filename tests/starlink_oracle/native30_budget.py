"""Pre-evaluation healthy native30 bound, not a fitted completion estimate.

100 MHz engine/control; one already configured job; no external arbitration;
the dedicated public AXI bench master must complete each transaction <=24
cycles. The bound includes capture transfer and reducer backpressure, not just
129*132 correlation issue cycles. No actual FFT or physical claim.
"""

CAPTURE_TRANSFER = 3 * 260 + 64  # ISSUE/WAIT/SEND per word + descriptor CDC/start
SAMPLE_ENERGY = 260 + 16  # every captured sample, synchronous read/MAC drain
PER_RAW_LAG = 132 + 16 + 16  # taps + read/MAC/flush/final/slide + reducer wait
CORRELATION_AND_REDUCER = 129 * PER_RAW_LAG
PUBLICATION = 128  # result-store/IRQ propagation; no occupied prior result
ENGINE_DERIVED_CYCLES = CAPTURE_TRANSFER + SAMPLE_ENERGY + CORRELATION_AND_REDUCER + PUBLICATION
ENGINE_LIMIT_CYCLES = 24_000
AXI_TRANSACTION_LIMIT = 24
READOUT_TRANSACTION_LIMIT = 140  # two 26-word indexed reads, release, telemetry
POST_CAPTURE_LIMIT_CYCLES = 28_000
CONTINUATION_RAW_COUNT = 4096
RAW_AFTER_CAPTURE = 8205 - 2779


def budget():
    assert ENGINE_DERIVED_CYCLES <= ENGINE_LIMIT_CYCLES
    assert ENGINE_LIMIT_CYCLES + AXI_TRANSACTION_LIMIT * READOUT_TRANSACTION_LIMIT <= POST_CAPTURE_LIMIT_CYCLES
    # Integer units: one raw sample = 100/30 engine cycles. Do not round
    # source support upward when admitting a finite continuation.
    available_tenths = (RAW_AFTER_CAPTURE + CONTINUATION_RAW_COUNT) * 100 // 3
    assert available_tenths >= POST_CAPTURE_LIMIT_CYCLES * 10
    return {
        "engine_derived_cycles": ENGINE_DERIVED_CYCLES,
        "engine_limit_cycles": ENGINE_LIMIT_CYCLES,
        "axi_transaction_limit_cycles": AXI_TRANSACTION_LIMIT,
        "readout_transaction_limit": READOUT_TRANSACTION_LIMIT,
        "post_capture_limit_cycles": POST_CAPTURE_LIMIT_CYCLES,
        "continuation_raw_count": CONTINUATION_RAW_COUNT,
        "raw_after_capture_before_continuation": RAW_AFTER_CAPTURE,
        "available_engine_tenths": available_tenths,
        "margin_engine_tenths": available_tenths - POST_CAPTURE_LIMIT_CYCLES * 10,
        "conditions": "healthy configured single job, free result store,100MHz, direct AXI master<=24cycles/transaction",
    }
