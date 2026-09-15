import pytest

from tools.review_glrt_cpu_continuity import review_continuity


SERIAL="1040005e0b100007100010000bf33a5d4d"
LOS=(1190312500,1940312500,1440312500,1690312500)


def evidence():
    rows=[f"plan 30000000 {SERIAL} {' '.join(map(str,LOS))} continuity30-after-scout16 4 400000000000"]
    snapshot=("GLT1SNAP 00010000 474c5431 000a2dfc 00000159 ce8315b0 00000430 "
              "00000002 00000000 00000000 00000000 00000000 00000000 00000000 "
              "00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
              "00000000 01c9c380 00009ab0 b04a2fab 00000001")
    epochs=[1,2,3,4]
    for number,(lo,outcome) in enumerate(((LOS[0],2),(LOS[0],1),(LOS[0],2),(LOS[0],0))):
        rows.append("snapshot "+snapshot)
        for kind,epoch,latest in (("before_tune",epochs[number],100+number*20),
                                  ("tuned",epochs[number],101+number*20),
                                  ("after_run",epochs[number]+1,110+number*20)):
            result=outcome if kind=="after_run" else 0
            rows.append(f"visit {kind} {number} {result} {lo} 30000000 {epoch} {latest} 1 1")
        if number==0: rows.append(f"segment start 0 1 0 {LOS[0]} retained_activity")
        if number==1: rows.append("segment terminal 0 1")
        if number==2: rows.append(f"segment start 1 3 0 {LOS[0]} native_handoff")
        if number==3: rows.append("segment terminal 1 0")
    rows.append("terminal 0")
    parent={"rate":30000000,"result":0,"rf_sample_limit":296091648,"scan_rounds":2,
            "segments_started":2,"visits_executed":4,"track_complete":1,
            "selection":"native_handoff","selected_index":0}
    return "\n".join(rows)+"\n",parent


def test_review_accepts_contiguous_rescan_and_completed_second_segment():
    text,parent=evidence()
    result=review_continuity(text,parent,serial=SERIAL,los=LOS)
    assert result=={"status":"pass","scope":"bounded_radio_local_continuity_transitions",
                    "scan_rounds":2,"segments":2,"visits":4,"rf_sample_limit":296091648}


@pytest.mark.parametrize("damage",["number","selection","outcome","sample_limit","fault","unknown"])
def test_review_rejects_damaged_transition_or_parent_claim(damage):
    text,parent=evidence()
    if damage=="number": text=text.replace("visit before_tune 2 ","visit before_tune 4 ")
    if damage=="selection": text=text.replace("segment start 1 3 0 1190312500","segment start 1 3 1 1190312500")
    if damage=="outcome": text=text.replace("segment terminal 0 1","segment terminal 0 3")
    if damage=="sample_limit": parent["rf_sample_limit"]+=1
    if damage=="fault": text=text.replace("00000002 00000000","00000002 00000001",1)
    if damage=="unknown": text=text.replace("segment terminal 1 0","mystery")
    with pytest.raises((ValueError,AssertionError)):
        review_continuity(text,parent,serial=SERIAL,los=LOS)
