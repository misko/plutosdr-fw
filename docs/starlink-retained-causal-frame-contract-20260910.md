# Retained actual frame-event correction — frozen acceptance proposal

This is a test-only correction to the v4 witness, not a runtime, result-guard,
numerical, clock, or service-budget change. The original v4 actual failure is
retained: job 1 accepted inputs at cycles 939, 941, and 942; `event_frame_started`
was observed at cycle 942. The former `actual_inputs == 1` check incorrectly
promoted the offline script's first-input event convention to a vendor contract.

[AMD PG109, May 4 2022](https://www.amd.com/content/dam/xilinx/support/documents/ip_documentation/xfft/v9_1/pg109-xfft.pdf),
printed pages 12 and 58, describes an internal frame-processing/load event;
AXI input data can already be buffered. It does not establish a universal
first-handshake, third-word, or +3-cycle rule. The accepted L1 CSV
`e7127798f315772b95aff63b75fffcd9cf5d1af8ca3c96e878bae4b39e443d71`
does not contain frame timing. Existing extracted WDB inventories do not prove it.

Before evaluation, the new contract requires all 40 admitted jobs (38 complete,
two aborted forward prefixes) to have exactly one known, one-sampled-cycle frame
pulse in their own admitted/configured, freshly released core-reset epoch.
At that event there must be at least one accepted physical input, counting a
same-edge input. The event must precede the first raw output strictly. The next
sample must observe a known-zero frame signal in the same active owner/reset
epoch. A `RACT_FRAME` receipt records admission, release, actual configuration,
event and closing sample coordinates, identity, and accepted inputs before/on/
after the event. These counts are joined independently to every numerical input
row, including an event on a cycle with no input handshake. Every reset-release
receipt is uniquely joined to its admission and actual configuration, not merely
counted. Exact existing release/admit+2, configuration/admit+3, physical input
first/admit+5, input span 513, raw-first/input-last+781, status at raw ordinal 2,
publication/admit+1810 and all global/guard budgets remain unchanged.

The historical offline script remains byte-identical. Directed test-only event
adapters may exercise first-input, idle-gap, later-input, and pre-output events;
they establish checker behavior only, not vendor event latency. Early, duplicate,
held, missing, raw-coincident, stale-owner/reset/configuration and counter-mutant
cases must reject. No diagnostic bypass or vendor retry is authorized by this
document. Model-specific observed offsets are reported as observations, never
fitted acceptance constants. The original v4 bundle, failed run, runtime, goldens,
clock settings, and numerical CSV schema remain untouched.
