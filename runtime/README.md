# Tandem AGC runtime

| File | Role |
|---|---|
| `spf_tandem_lifecycle.{c,h}` | Ownership lifecycle. Pure state machine — no syscalls, no I/O. A transposition of RC17's `spf_ip_rx_lifecycle`. |
| `spf_tandem_ctl.{c,h}` | The §11 enable and disable transactions, over a backend interface. |
| `spf_tandem_iio.c` | The real backend, over libiio. Compiled only where libiio exists. |
| `spf_gainctl.c` | `spf-gainctl`, the operator CLI. |

## Build and test

    cmake -S . -B build -DBUILD_TESTING=ON && cmake --build build
    ctest --test-dir build --output-on-failure

Two suites, 18 tests, ~1350 checks, `-Wall -Wextra -Werror`.

The reason the tests need no radio is the backend indirection: the transaction
logic never touches hardware directly, so §8.4's failure list — an SPI failure
at each step, unequal read-back, an ownership timeout, split-table mode, the
wrong ENSM state — is all reachable against a mock.

## Two hardware facts this code enforces

Both measured by experiment E-AGC1 on both radios, and both the kind of thing
that is invisible until it bites:

**`CTRL_IN` edges are ignored unless the ENSM is RX-active.** Arming outside RX
gives a controller that believes it owns gain while every edge it emits does
nothing. So RX-active is a precondition of enabling, checked before anything is
armed, and an ENSM transition *out* of RX while armed is treated as a
synchronisation fault rather than ignored — the pins go deaf without faulting
anything, so the index model would drift with nothing local to notice.

**Arming takes gain away from software, silently.** With `0x0FB[1:0]` set, a
`hardwaregain` write returns success and is dropped, and the readback reports
the pin-controlled index. A caller that does not verify readback would believe
it had set the gain. The runtime therefore refuses such writes itself rather
than relying on the device to refuse them; silent success is worse than an
error.

## One convention worth not rediscovering

Every AD9361 register write is read-modify-write. `direct_reg_access` writes the
whole byte, and E-AGC1 found bit 3 of `0x0FB` live on the shipped builds, so a
bare `0x03` would have cleared it. `0x0FE` is worse: its low five bits are the
Peak Overload Wait Time, so writing a step size carelessly destroys the
detector blanking window. Tests assert both survive.
