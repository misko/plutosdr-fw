# Bounded scheduled native commissioning

`starlink_glrt_schedule_capture.py` exercises two finite native batches of 32
and 64 repeats at 750 Hz, with a clear/rebase between them. Each admitted job
uses the full 79,200-sample engine. It waits for complete batch retirement before
draining, so the second batch also exercises the full 64-record result queue.
It does not claim to acquire a pilot or provide accuracy evidence.

Run it only through the PPU `glrt_canary --scheduled-batches` operator after a
scheduled FPGA image passes the complete-board gates, is packaged and pinned,
and is deployed through PPU to `.14`. The operator holds the shared radio lease,
attests exact firmware and Ethernet identity, validates GLF1/GLN1/GLS1 idle
ownership, configures the requested RX state and runs actual 60 MS/s RX
calibration. It independently checks the final cleared GLS1 state after the
collector returns. No scheduled image is registered by this collector change.

The collector requires exact endpoint `ip:192.168.1.14` and serial
`winbond-db620818a328172c`. No USB enumeration occurs. Firmware version, RX LO,
bandwidth and TX-off state are checked before writes. Initial scheduling lead
is 1,200,000 native samples (20 ms); future batches expire at the last sample
of their last permitted pilot. All work is finite even if Ethernet stalls.
The operator imposes a 60-second process timeout followed by bounded cleanup.

Each batch retains its descriptor and submission text before SUBMIT. A failure
after SUBMIT is uncertain and is never automatically retried. Every raw head is
saved and fsynced before its exact epoch/sequence acknowledgement. The head is
read twice to confirm immutable caching, then checked against the original
finite descriptor's start, phase, tag and repeat. Faulted/partial observations
remain retained and acknowledged but cannot produce a passing batch. Badly
formed or unassociated heads are retained without POP. Final snapshots prove
all opportunities accounted for and all admitted results drained.

Failure cleanup cancels future work but never silently discards unacknowledged
results. A remaining head/reservation makes cleanup fail explicitly; retain the
output directory and reconcile the descriptor/head/snapshots before attempting
another run. Successful completion clears counters and invalidates the source
epoch, retains the base/manual idle profile and checks unchanged RF settings.

The firmware tests cover both CLI entry points, retained-before-POP ordering,
uncertain submission, stale/corrupt/changing heads, explicit dropped repeats,
deadline expiry, two generations, final cleanup and profile mismatch without
mutation. The PPU tests cover calibration, Ethernet-only identity and lease,
bounded child execution, final cleared-state attestation and failure receipts.

The kernel parser accepts the single terminal NUL included by libiio's string
attribute writer (`strlen(src)+1`), while rejecting embedded NULs and trailing
hidden data. Kernel `42fb1cd17aff` is the first scheduled driver commit with
this interoperability correction; do not use the earlier scheduled kernel for
Ethernet commissioning.

Remaining evidence after a passing scheduled canary includes fresh manual
original-IQ replay on that same firmware, radio-local causal feedback and loss
accounting, live acquisition association and a bounded real-signal precision
comparison. A transport pass does not satisfy those release gates.
