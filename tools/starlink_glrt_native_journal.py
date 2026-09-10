"""Internal GLRJ1 evidence review and retained recovery through the GLS1 port.

No radio discovery, process management, acquisition or RF configuration. The
external PPU owner must confirm the writer has stopped before recovery.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass

from .starlink_glrt_schedule_abi import SAMPLES, ScheduleBatch, ScheduleSnapshot, ScheduledResult

KINDS = {"bootstrap_seed", "initial", "descriptor", "head", "estimate", "before_submit",
         "stopping", "drained", "final", "snapshot"}


@dataclass(frozen=True)
class JournalRecord:
    kind: str
    payload: bytes


def records(data: bytes, *, allow_partial: bool = False) -> tuple[list[JournalRecord], bool]:
    if not data.startswith(b"GLRJ1\n") or len(data) > 128*1024*1024:
        raise ValueError("invalid or oversized GLRJ1 journal")
    result = []
    at = 6
    while at < len(data):
        end = data.find(b"\n", at, at+80)
        if end < 0:
            if allow_partial and len(data)-at < 80:
                return result, True
            raise ValueError("truncated or invalid journal header")
        match = re.fullmatch(rb"([a-z_]{1,32}) ([0-9]{1,4})", data[at:end])
        if not match or match[1].decode() not in KINDS or int(match[2]) > 4096:
            raise ValueError("invalid journal kind or length")
        size = int(match[2])
        if end+1+size > len(data):
            if allow_partial:
                return result, True
            raise ValueError("truncated journal payload")
        result.append(JournalRecord(match[1].decode(), data[end+1:end+1+size]))
        at = end+1+size
    return result, False


def batch(text: str) -> ScheduleBatch:
    fields = text.split()
    if len(fields) != 10 or not all(re.fullmatch(r"[0-9a-fA-F]{1,16}", s) for s in fields):
        raise ValueError("invalid retained GLS1 descriptor")
    b = ScheduleBatch(*[int(s, 16) for s in fields])
    if b.prediction(b.repeats-1)[0]+SAMPLES-1 > min(b.expires, 2**64-1):
        raise ValueError("retained descriptor exceeds expiry or source range")
    return b


def descriptors(entries: list[JournalRecord], *, epoch: int) -> dict[int, tuple[int, ScheduleBatch]]:
    owners: dict[int, tuple[int, ScheduleBatch]] = {}
    next_frame = 0
    for record in entries:
        if record.kind != "descriptor":
            continue
        fields = record.payload.decode("ascii").split(maxsplit=2)
        if len(fields) != 3 or fields[0] != "frame" or not re.fullmatch(r"[0-9]{1,6}", fields[1]):
            raise ValueError("invalid retained global frame mapping")
        first, b = int(fields[1]), batch(fields[2])
        if b.epoch != epoch or b.tag in owners or first != next_frame or first+b.repeats > 225000:
            raise ValueError("retained descriptor ownership is inconsistent")
        owners[b.tag] = first, b
        next_frame += b.repeats
    return owners


def review(data: bytes, *, epoch: int) -> dict:
    """Require a complete retained drain and final clear, independent of C state.

    This checks transport/association and finite fit fields. It does not repeat
    the numerical solver or establish pilot detection or physical accuracy.
    """
    entries, _ = records(data)
    owners = descriptors(entries, epoch=epoch)
    seen: set[int] = set()
    heads = []
    estimates = []
    pending = None
    drained = final = None
    for record in entries:
        text = record.payload.decode("ascii")
        if final is not None:
            raise ValueError("records follow final clearance")
        if record.kind == "descriptor":
            # Only descriptors already retained at this point authorize heads.
            seen.add(batch(text.split(maxsplit=2)[2]).tag)
        elif record.kind == "head":
            if pending is not None:
                raise ValueError("retained head lacks associated estimate")
            head = ScheduledResult.from_sysfs(text)
            if head.tag not in seen:
                raise ValueError("head precedes retained ownership")
            first, b = owners[head.tag]
            head.require_association(b, sequence=len(heads))
            pending = (head, first+head.repeat)
            heads.append(head)
        elif record.kind == "estimate":
            fields = text.split()
            if pending is None or len(fields) != 9:
                raise ValueError("estimate lacks retained head")
            head, frame = pending
            if any(not re.fullmatch(r"[0-9]{1,10}", fields[n]) for n in (0, 1, 2, 8)):
                raise ValueError("malformed estimate identity or rejection")
            if tuple(map(int, fields[:3])) != (epoch, head.sequence, frame):
                raise ValueError("estimate association differs from head")
            values = list(map(float, fields[3:8]))
            if not all(math.isfinite(v) for v in values) or int(fields[8]) & ~127:
                raise ValueError("nonfinite fit or unknown rejection")
            estimates.append(dict(epoch=epoch, sequence=head.sequence, frame=frame,
                delay_s=values[0], residual_hz=values[1], cfo_hz=values[2], coherence=values[3],
                linearized_coherence=values[4], rejection=int(fields[8])))
            pending = None
        elif record.kind in {"initial", "before_submit", "stopping", "drained", "final"}:
            state = ScheduleSnapshot.from_sysfs(text)
            if state.epoch != epoch:
                raise ValueError("journal crosses source epoch")
            if record.kind == "drained":
                state.require_drained()
                if pending is not None or state.popped != len(heads):
                    raise ValueError("retained heads do not cover drained inventory")
                drained = state
            elif record.kind == "final":
                state.require_drained()
                if (drained is None or drained.popped != len(heads) or state.configured or
                        state.faults or state.status & 16):
                    raise ValueError("missing retained drain or uncleared final state")
                final = state
    if pending is not None or final is None or entries[-1].kind != "final":
        raise ValueError("journal has no complete verified ending")
    return dict(heads=heads, estimates=estimates, descriptors=owners, drained=drained, final=final,
                supported=sum(e["rejection"] == 0 for e in estimates))


def recover(device, data: bytes, *, epoch: int, writer_stopped: bool, retain,
            deadline: float, clock=time.monotonic, sleep=time.sleep) -> ScheduleSnapshot:
    """Cancel, retain/associate outstanding heads, drain, then clear.

    The caller retains every callback payload before it returns. No uncertain
    POP is retried: snapshot reconciliation can establish one completed POP,
    otherwise recovery stops and leaves that head. Never run with a live writer.
    """
    if not writer_stopped:
        raise ValueError("recovery requires a confirmed stopped writer")
    entries, _ = records(data, allow_partial=True)
    owners = descriptors(entries, epoch=epoch)

    def snap():
        if clock() >= deadline:
            raise TimeoutError("retained recovery deadline")
        raw = device.read("native_schedule_snapshot")
        retain("snapshot", raw)
        state = ScheduleSnapshot.from_sysfs(raw)
        if state.epoch != epoch:
            raise ValueError("recovery source epoch changed")
        return state

    state = snap()
    device.command("native_schedule_command", 2)
    while True:
        state = snap()
        if not state.status & 4 and state.admitted == state.committed:
            break
        sleep(.002)
    while state.queued:
        raw = device.read("native_schedule_result")
        retain("head", raw)
        head = ScheduledResult.from_sysfs(raw)
        if head.tag not in owners:
            raise ValueError("recovery head has no retained descriptor")
        head.require_association(owners[head.tag][1], sequence=state.popped)
        if device.read("native_schedule_result") != raw:
            raise ValueError("recovery head changed before POP")
        try:
            device.command("native_schedule_pop", head.acknowledgement().strip())
        except (OSError, RuntimeError):
            after = snap()
            if after.popped != state.popped+1:
                raise
        state = snap()
        if state.popped != head.sequence+1:
            raise ValueError("recovery POP did not advance exactly one head")
    state.require_drained()
    device.command("native_schedule_command", 4)
    final = snap()
    final.require_drained()
    if final.configured or final.faults or final.status & 16:
        raise ValueError("recovery failed to clear drained source")
    return final
