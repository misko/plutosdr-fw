# Gain-series v4 RC10 timestamp-state candidate

RC10 is an unpromoted, RAM-boot-only candidate. It retains RC9's registered
timestamp decision, which removes the failed DMA-ready timing path, while
preserving the original semantics of a rejected timestamp interval.

## RC9 pre-deployment audit finding

RC9 intentionally held each timestamp word for one DMA clock while its 64-bit
range decision was registered. Its first implementation reused the existing
discard register for both the one-word decision and the complete interval
state. It cleared that register at the timestamp handshake. Consequently, a
rejected timestamp could be counted correctly but the following payload words
would no longer be suppressed.

Current gain-series operation leaves TX timestamp insertion disabled, so this
could not corrupt today's gain-metadata captures. It nevertheless violates the
timestamp transport contract and is unacceptable in a candidate intended to
retain timestamp support. RC9 was therefore not deployed to hardware.

## RC10 change

RC10 separates three states:

- `timestamp_decision_valid`: the held timestamp has a registered decision;
- `timestamp_decision_discard`: that timestamp word is outside the accepted
  range; and
- `timestamp_check_discard`: the accepted decision for the complete payload
  interval.

The first two registers isolate the 64-bit comparison from DMA `ready`. At the
timestamp handshake, the decision is copied into the persistent interval
state. A rejected interval remains ready toward DMA but cannot write the FIFO.
The next accepted timestamp replaces the interval state and restores FIFO
writes. Timestamp-disabled IQ remains an immediate transparent path.

The focused simulation now proves all of the following:

- timestamp decisions take one registered evaluation cycle;
- a valid timestamp is not counted;
- an invalid timestamp is counted exactly once;
- all four following payload words are accepted from DMA but suppressed from
  the FIFO;
- a subsequent valid timestamp restores FIFO writes; and
- disabling timestamping remains transparent and cannot change the count.

All prior counter-CDC, FIFO-reset, TX-diagnostic, and disabled-timestamp tests
remain mandatory. Positive routed setup and hold slack are required before
RC10 may be RAM-booted. Never write this candidate to QSPI.
