"""Evidence gate for a new finite native acquisition after a clean episode.

The PPU owner retains the complete journal and confirms process termination
before calling this numerical/protocol gate. This module performs no device
I/O, REBASE, retries or process management. Source/transport failures require
explicit recovery; only normal completion or acquisition loss permits restart.
"""
from __future__ import annotations

from dataclasses import dataclass

from .starlink_glrt_native_journal import review
from .starlink_glrt_schedule_abi import ScheduleSnapshot


@dataclass(frozen=True)
class RestartFence:
    epoch: int
    native_sample: int

    def require_fresh_observations(self, starts: tuple[int, ...]) -> None:
        """All 24 complete observation windows must start after termination.

        Coordinates include the observation's real left filter/timing guard;
        supplying nominal frame epochs here would permit reused pre-stop IQ.
        Acquisition identity, support and prediction gates remain mandatory.
        """
        if len(starts) != 24 or any(
            type(value) is not int or not self.native_sample < value < 2**64
            for value in starts
        ) or any(a >= b for a, b in zip(starts, starts[1:])):
            raise ValueError("reacquisition requires 24 new ordered observation windows")


def restart_fence(data: bytes, *, epoch: int, result: int, configured: int,
                  retained_popped: int, writer_stopped: bool,
                  current: ScheduleSnapshot) -> RestartFence:
    """Require a complete, fault-free, cleared ending and a current source fence."""
    if writer_stopped is not True:
        raise ValueError("restart requires a confirmed stopped writer")
    if type(result) is not int or result not in (0, -4):
        raise ValueError("source, deadline, protocol or transport failure cannot auto-restart")
    if any(type(value) is not int or not 0 < value <= 225000
           for value in (configured, retained_popped)):
        raise ValueError("restart requires a nonempty bounded retained episode")
    checked = review(data, epoch=epoch)
    for head in checked['heads']:
        head.require_complete()
    drained, final = checked['drained'], checked['final']
    if not (configured == retained_popped == len(checked['heads']) == drained.configured
            == drained.admitted == drained.committed == drained.popped):
        raise ValueError("runtime and retained terminal inventories differ")
    if any((drained.faults, drained.cdc_drops, drained.pacer_drops,
            drained.late, drained.no_space, drained.unavailable, drained.expired,
            drained.cancelled, final.cdc_drops, final.pacer_drops)):
        raise ValueError("loss or faults prevent automatic restart")
    current.require_drained()
    if (current.epoch != epoch or current.latest_index < final.latest_index
            or final.latest_index < drained.latest_index
            or current.status & ~1 != 0x22 or current.configured or current.faults
            or current.cdc_drops or current.pacer_drops):
        raise ValueError("restart requires a current healthy cleared source in the same epoch")
    if not 0 < epoch < 2**32-1:
        raise ValueError("no next source epoch available")
    return RestartFence(epoch, current.latest_index)
