# Native60 readback-only correction contract

This is offline preparation, not authorization to execute corrected service.
Original command interval[34359738560,34359738720], lead[1535,1695], <=256
control-cycle admission deadline,16,423 source/no tail,264/520/257/241 geometry,
84,000 publication/full-drain and88,000 readout deadlines remain unchanged.

Print-only diagnostic original chunk10ed81 returned simulator/launcher exit1
in0.2249s at the unchanged assertion, cycle8295/source3357. No command/capture/
raw tuple was admitted. Two actual readbacks confirmed the low-read snapshot:

| Observation | Cycle | Public64 | Live offered index | Synchronized index | Retained low-read snapshot |
|---|---:|---|---|---|---|
| after_lo | 8288 | xxxxxxxx000000bf | 00000008000000c3 | 00000008000000c2 | 00000008000000bf |
| after_hi | 8295 | 00000008000000bf | 00000008000000c7 | 00000008000000c6 | 00000008000000bf |

The unassigned public high half after only the low read is expected; after both
reads public64 is known and coherent. Index34359738559 is one behind the fixed
trigger34359738560. It is not evidence of a late command (none was submitted).
The original assertion incorrectly reused the real-handshake lower bound for
a deliberately delayed software snapshot. README explicitly permits CDC lag.

Full diagnostic241 files/6,294,090 bytes remain under
`/tmp/starlink-bank-route.I50MDJ/main-native60-service-diag-v1`, with compile0,
zero diagnostics, simulator1, no success terminal and equal before/after source
and69-fixture hashes. Archive
`reports/experiments/20260910-native60-service-diag-v1.tgz`,1,710,730 bytes,
SHA `21060d0248c0024f3522f6343b04d8d59f2ed157cdd2d4161622feb80aaf15af`.
Archive full readback against original files passes. Original v1 failure and
its separate archive/report remain unchanged. No diagnostic retry occurred.

## New readback check, independently bounded from handshake eligibility

Observe once, on the control clock, the exact accepted low-register condition:
known `up_rreq && !register_read_pending && !result_read_pending &&
!telemetry_read_pending && up_raddr==6`. Record the current64-bit synchronized
index BEFORE nonblocking updates, current offered raw index and control cycle.
All request/pending/address/value flags must be known; source enable/strobe must
be healthy. No hierarchy write, force, injected tuple, additional public read
or altered sample timing is needed. At completed low/high public readback,
require exact64-bit equality to that one capture witness and to the retained
hardware snapshot; a duplicate/missing capture or changed high half fails.

At a low-register capture, old synchronizer2 reflects Gray sampled two100MHz
edges earlier. Offered source index leads accepted source by half a source
period. The ideal fixed-phase simulation lag bound is therefore
`ceil((2*10000000 + 8333333)/16666666) = 2` raw samples. Require no future index
before subtracting and require the lag in[0,2]. There is no arbitrary widening
of the actual command-handshake interval.

Each unchanged AXI helper transaction has a24-control-cycle bound. From actual
low capture to completing both reads,48 cycles conservatively cover the
remaining first transaction and second transaction. The extra source movement
is at most `ceil(48*10000000/16666666)=29`, hence returned-snapshot lag[0,31].
Require known, nonfuture values, monotonic live source index, <=48 elapsed
cycles, and exact pair coherence. These are separate readback age/correctness
checks, not a relaxation of command lead. Actual scheduler admission is still
checked against the original fixed interval and original signed lead range.

These bounds describe ideal digital scheduling under the frozen60/100MHz
clocks; they do not characterize physical synchronizer metastability or
hardware latency. The additive machine contract is
`tests/starlink_oracle/native60_readback_contract.py`; the original committed
native60_budget_recipe.py and all69 numerical files remain unchanged.
