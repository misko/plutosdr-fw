"""Independent review of bounded radio-local continuity visit journals."""

import math

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
    policy=parent.get("activity_selection","first_qualified")
    wait100=policy=="strongest_one_attempt_scan_power50_wait12_track100"
    wait=policy=="strongest_one_attempt_scan_prior_reacquire_wait12"
    prior=policy in ("strongest_one_attempt_scan_prior_reacquire",
                     "strongest_one_attempt_scan_prior_reacquire_wait12")
    ranked=policy in ("strongest_complete_scan","strongest_one_attempt_scan",
                      "strongest_one_attempt_scan_prior_reacquire",
                      "strongest_one_attempt_scan_prior_reacquire_wait12") or wait100
    fresh=policy in ("strongest_one_attempt_scan","strongest_one_attempt_scan_prior_reacquire",
                     "strongest_one_attempt_scan_prior_reacquire_wait12")
    fresh=fresh or wait100
    profile=("sparse100-wait12-after-scout1" if wait100 else
             "continuity30-prior-wait12-after-scout1" if wait else
             "continuity30-prior-after-scout1" if prior else
             "continuity30-fresh-after-scout1" if fresh else
             "continuity30-ranked-after-scout16" if ranked else "continuity30-after-scout16")
    expected_scope=("bounded_arm_scout_wait100_followup" if wait100 else
                    "bounded_arm_scout_prior_wait_segmented_followup" if wait else
                    "bounded_arm_scout_prior_segmented_followup" if prior else
                    "bounded_arm_scout_fresh_segmented_followup" if fresh else
                    "bounded_arm_scout_ranked_segmented_followup" if ranked else
                    "bounded_arm_scout_segmented_followup")
    if parent.get("scope")!=expected_scope:
        raise ValueError("continuity scope differs")
    expected=["plan",str(parent["rate"]),serial,*map(str,los),profile,
              str(count),"1200000000000" if wait100 else "900000000000" if wait else "400000000000"]
    if plan!=expected or terminals[0] != ["terminal",str(parent["result"])]:
        raise ValueError("visit plan identity differs")

    snapshots=[];visits=[];starts=[];ends=[];candidates=[]
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
        elif fields[:2]==["activity","candidate"] and len(fields)==4:
            number=int(fields[2]);score=float(fields[3])
            if not math.isfinite(score) or not 0.015<=score<=1:
                raise ValueError("activity score differs")
            candidates.append((number,score))
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
    if parent["scan_rounds"]>(12 if wait or wait100 else 3) or parent["segments_started"]>(1 if wait100 else 3):
        raise ValueError("continuity plan bound differs")
    previous_followup=-1;previous_round=-1
    for start,end in zip(starts,ends,strict=True):
        round_number,followup,selected,lo,selection=start
        if not previous_round<round_number<parent["scan_rounds"] or end[0]!=round_number or followup<=previous_followup:
            raise ValueError("segment order differs")
        round_first=previous_followup+1+(round_number-previous_round-1)*count
        expected_followup=round_first+count if ranked and selection=="retained_activity" else round_first+selected+1
        if not 0<=selected<count or followup!=expected_followup or lo!=los[selected]:
            raise ValueError("segment scout selection differs")
        scout=grouped[round_first+selected][-1];track=grouped[followup][-1]
        expected_scout=0 if ranked and selection=="retained_activity" else 2
        mapped_track=(track[2] if track[2] in (0,1,3) else -4)
        if (scout[2]!=expected_scout or abs(scout[3]-lo)>16 or abs(track[3]-lo)>16 or
                mapped_track!=end[1]):
            raise ValueError("segment transition disposition differs")
        round_candidates=[row for row in candidates if round_first<=row[0]<followup]
        if ranked and selection=="retained_activity":
            if not round_candidates or max(round_candidates,key=lambda row:(row[1],-row[0]))[0]!=round_first+selected:
                raise ValueError("strongest activity selection differs")
            if wait100 and max(score for _,score in round_candidates)<0.05:
                raise ValueError("100-second activity floor differs")
        previous_followup=followup;previous_round=round_number
    if parent["segments_started"]:
        if parent["selected_index"]!=starts[-1][2] or parent["selection"]!=starts[-1][4]:
            raise ValueError("parent selection differs")
    elif parent["selected_index"] is not None or parent["selection"]!="none":
        raise ValueError("empty parent selection differs")
    expected_visits=(parent["scan_rounds"]*count if not starts else
        previous_followup+1+(parent["scan_rounds"]-previous_round-1)*count)
    if parent["visits_executed"]!=expected_visits:
        raise ValueError("scan round visit accounting differs")
    scouts=parent["visits_executed"]-parent["segments_started"]
    expected_limit=scouts*25165824+parent["segments_started"]*(737280000 if wait100 else 122880000)
    if parent["rf_sample_limit"]!=expected_limit:
        raise ValueError("parent sample accounting differs")
    if bool(parent["track_complete"]) != bool(ends and ends[-1][1]==0):
        raise ValueError("parent completion differs")
    return {"status":"pass","scope":"bounded_radio_local_continuity_transitions",
            "scan_rounds":parent["scan_rounds"],"segments":len(starts),
            "visits":len(grouped),"rf_sample_limit":expected_limit,
            "activity_selection":policy}
