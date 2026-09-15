"""Independent review of the bounded radio-local continuity visit journal."""

from .starlink_glrt_tracking_abi import TrackingSnapshot


def review_continuity(text, parent, *, serial, los):
    if not isinstance(text, str) or not text.endswith("\n") or "\x00" in text:
        raise ValueError("visit journal framing differs")
    lines=text.splitlines()
    plans=[line.split() for line in lines if line.startswith("plan ")]
    terminals=[line.split() for line in lines if line.startswith("terminal ")]
    if len(plans)!=1 or len(terminals)!=1 or lines[0] != " ".join(plans[0]) or lines[-1] != " ".join(terminals[0]):
        raise ValueError("visit journal plan or terminal differs")
    plan=plans[0];count=len(los)
    expected=["plan",str(parent["rate"]),serial,*map(str,los),"continuity30-after-scout16",
              str(count),"400000000000"]
    if plan!=expected or terminals[0] != ["terminal",str(parent["result"])]:
        raise ValueError("visit plan identity differs")

    snapshots=[];visits=[];starts=[];ends=[]
    for line in lines[1:-1]:
        fields=line.split()
        if line.startswith("snapshot "):
            state=TrackingSnapshot.from_sysfs(line.split(" ",1)[1]);state.require_drained()
            if state.rate!=parent["rate"] or state.faults or state.cdc_drops or state.pacer_drops:
                raise ValueError("visit boundary snapshot differs")
            snapshots.append(state)
        elif fields[:1]==["visit"] and len(fields)==10:
            kind=fields[1]
            if kind not in ("before_tune","tuned","after_run"):
                raise ValueError("visit boundary kind differs")
            visits.append((kind,*map(int,fields[2:])))
        elif fields[:2]==["segment","start"] and len(fields)==7:
            if fields[6] not in ("retained_activity","native_handoff"):
                raise ValueError("segment selection differs")
            starts.append((*map(int,fields[2:6]),fields[6]))
        elif fields[:2]==["segment","terminal"] and len(fields)==4:
            ends.append(tuple(map(int,fields[2:])))
        else:
            raise ValueError("unknown visit journal record")
    if not snapshots:
        raise ValueError("visit snapshots absent")
    grouped={}
    for row in visits:
        grouped.setdefault(row[1],[]).append(row)
    expected_numbers=list(range(parent["visits_executed"]))
    if sorted(grouped)!=expected_numbers:
        raise ValueError("visit evidence numbering differs")
    for number in expected_numbers:
        rows=grouped[number]
        if [r[0] for r in rows] != ["before_tune","tuned","after_run"]:
            raise ValueError("visit boundary sequence differs")
        if any(r[1]!=number or r[4]!=parent["rate"] or r[7:]!=(1,1) for r in rows):
            raise ValueError("visit boundary identity differs")
        if rows[1][3] != rows[2][3]:
            raise ValueError("visit LO changed during child")
        if rows[2][5] <= rows[1][5] or rows[2][6] <= rows[1][6]:
            raise ValueError("visit source did not advance")
    if not len(starts)==len(ends)==parent["segments_started"]:
        raise ValueError("segment count differs")
    previous_followup=-1
    for expected_round,(start,end) in enumerate(zip(starts,ends,strict=True)):
        round_number,followup,selected,lo,selection=start
        if round_number!=expected_round or end[0]!=expected_round or followup<=previous_followup:
            raise ValueError("segment order differs")
        round_first=previous_followup+1
        if not 0<=selected<count or followup!=round_first+selected+1 or lo!=los[selected]:
            raise ValueError("segment scout selection differs")
        scout=grouped[followup-1][-1];track=grouped[followup][-1]
        if scout[2]!=2 or scout[3]!=lo or track[3]!=lo or track[2]!=end[1]:
            raise ValueError("segment transition disposition differs")
        previous_followup=followup
    if parent["segments_started"]:
        if parent["selected_index"]!=starts[-1][2] or parent["selection"]!=starts[-1][4]:
            raise ValueError("parent selection differs")
    elif parent["selected_index"] is not None or parent["selection"]!="none":
        raise ValueError("empty parent selection differs")
    scouts=parent["visits_executed"]-parent["segments_started"]
    expected_limit=scouts*25165824+parent["segments_started"]*122880000
    if parent["rf_sample_limit"]!=expected_limit:
        raise ValueError("parent sample accounting differs")
    if bool(parent["track_complete"]) != bool(ends and ends[-1][1]==0):
        raise ValueError("parent completion differs")
    return {"status":"pass","scope":"bounded_radio_local_continuity_transitions",
            "scan_rounds":parent["scan_rounds"],"segments":len(starts),
            "visits":len(grouped),"rf_sample_limit":expected_limit}
