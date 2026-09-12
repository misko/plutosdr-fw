"""Internal retained GLTH1 predictor state; source evidence is attested separately."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import struct

from .starlink_glrt_tracking_abi import bank_id


@dataclass(frozen=True)
class TrackingHandoff:
    rate: int
    epoch: int
    first: int
    limit: int
    history_first: int
    last_seen: int
    last_supported: int
    anchor: int
    next_slot: int
    observations: tuple[tuple[int, float, float], ...]


def decode(data: bytes, *, epoch: int, rate: int) -> TrackingHandoff:
    """Check storage/order/forecast bounds, not the truth of imported estimates.

    Binary64 values use fixed hexadecimal bit strings in physical ring order,
    independent of host byte order. Earlier raw IQ/moments remain separate
    retained provenance; this record says exactly which state was transferred.
    """
    bank_id(rate)
    if len(data)>4096 or not data.endswith(b"\n"):
        raise ValueError("invalid tracking handoff extent")
    lines=data.decode("ascii").splitlines()
    fields=lines[0].split() if lines else []
    if (len(fields)!=12 or fields[:2]!=["GLTH1","00010000"] or
            any(not re.fullmatch(r"[0-9a-f]{16}" if i==9 else r"[0-9a-f]{8}",field)
                for i,field in enumerate(fields[2:],2))):
        raise ValueError("invalid tracking handoff header")
    r,e,first,limit,hfirst,seen,supported,anchor,count,next_slot=map(lambda s:int(s,16),fields[2:])
    if ((r,e)!=(rate,epoch) or not epoch or not 8<=count<=96 or next_slot>=96 or
            (count<96 and next_slot!=count) or len(lines)!=count+1 or
            not hfirst<=supported<=seen<first<limit or limit-first>225000 or
            limit-1-hfirst>1350000 or first-supported>32):
        raise ValueError("tracking handoff profile, storage or horizon invalid")
    observations=[]
    for line in lines[1:]:
        if not re.fullmatch(r"[0-9a-f]{40}",line):
            raise ValueError("invalid tracking handoff observation")
        frame=int(line[:8],16)
        offset,cfo=(struct.unpack(">d",bytes.fromhex(line[i:i+16]))[0] for i in (8,24))
        if (not hfirst<=frame<=supported or not math.isfinite(offset) or not math.isfinite(cfo) or
                abs(offset)>rate*(5/3+250e-9)+1 or abs(cfo)+250>=rate/2):
            raise ValueError("invalid tracking handoff estimate")
        observations.append((frame,offset,cfo))
    chronological=observations[next_slot:]+observations[:next_slot] if count==96 else observations
    if (any(a[0]>=b[0] for a,b in zip(chronological,chronological[1:])) or
            chronological[-1][0]!=supported or sum(supported-row[0]<96 for row in observations)<8):
        raise ValueError("tracking handoff history order or support invalid")
    return TrackingHandoff(rate,epoch,first,limit,hfirst,seen,supported,anchor,next_slot,tuple(observations))
