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
    parent={"scope":"bounded_arm_scout_segmented_followup","rate":30000000,"result":0,
            "rf_sample_limit":296091648,"scan_rounds":2,
            "segments_started":2,"visits_executed":4,"track_complete":1,
            "selection":"native_handoff","selected_index":0}
    return "\n".join(rows)+"\n",parent


def test_review_accepts_contiguous_rescan_and_completed_second_segment():
    text,parent=evidence()
    result=review_continuity(text,parent,serial=SERIAL,los=LOS)
    assert result=={"status":"pass","scope":"bounded_radio_local_continuity_transitions",
                    "scan_rounds":2,"segments":2,"visits":4,"rf_sample_limit":296091648,
                    "activity_selection":"first_qualified"}


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


def test_ranked_review_requires_full_scan_and_selects_strongest_activity():
    text,parent=evidence()
    text=text.replace("continuity30-after-scout16","continuity30-ranked-after-scout16")
    text=text.replace("segment start 0 1 0 1190312500 retained_activity",
        "activity candidate 0 0.04\nactivity candidate 1 0.07\n"
        "segment start 0 4 1 1940312500 retained_activity")
    # Supply the two extra completed scouts and shift the old follow-ups/second
    # round out of this single completed ranked round.
    lines=text.splitlines();kept=[lines[0]]
    snapshot=next(line for line in lines if line.startswith("snapshot "))
    for number,lo in enumerate(LOS):
        kept.append(snapshot)
        for kind,epoch,latest in (("before_tune",1,100+number*20),("tuned",1,101+number*20),("after_run",2,110+number*20)):
            kept.append(f"visit {kind} {number} 0 {lo} 30000000 {epoch} {latest} 1 1")
        if number==0: kept.append("activity candidate 0 0.04")
        if number==1: kept.append("activity candidate 1 0.07")
    kept.extend([f"segment start 0 4 1 {LOS[1]} retained_activity",snapshot])
    for kind,epoch,latest in (("before_tune",2,200),("tuned",2,201),("after_run",3,210)):
        kept.append(f"visit {kind} 4 {0 if kind!='after_run' else 0} {LOS[1]} 30000000 {epoch} {latest} 1 1")
    kept.extend(["segment terminal 0 0","terminal 0"]);text="\n".join(kept)+"\n"
    parent.update(scope="bounded_arm_scout_ranked_segmented_followup",rf_sample_limit=223543296,
        scan_rounds=1,segments_started=1,visits_executed=5,track_complete=1,
        selection="retained_activity",selected_index=1,activity_selection="strongest_complete_scan")
    result=review_continuity(text,parent,serial=SERIAL,los=LOS)
    assert result["activity_selection"]=="strongest_complete_scan"
    with pytest.raises(ValueError):
        review_continuity(text.replace("candidate 1 0.07","candidate 1 0.03"),parent,serial=SERIAL,los=LOS)
    fresh=text.replace("continuity30-ranked-after-scout16","continuity30-fresh-after-scout1")
    fresh_parent={**parent,"scope":"bounded_arm_scout_fresh_segmented_followup",
                  "activity_selection":"strongest_one_attempt_scan"}
    assert review_continuity(fresh,fresh_parent,serial=SERIAL,los=LOS)["activity_selection"]=="strongest_one_attempt_scan"
    prior=fresh.replace("continuity30-fresh-after-scout1","continuity30-prior-after-scout1")
    prior_parent={**parent,"scope":"bounded_arm_scout_prior_segmented_followup",
                  "activity_selection":"strongest_one_attempt_scan_prior_reacquire"}
    assert review_continuity(prior,prior_parent,serial=SERIAL,los=LOS)["activity_selection"]==(
        "strongest_one_attempt_scan_prior_reacquire")
    wait=prior.replace("continuity30-prior-after-scout1","continuity30-prior-wait12-after-scout1")
    wait=wait.replace(" 400000000000\n"," 900000000000\n",1)
    wait_parent={**parent,"scope":"bounded_arm_scout_prior_wait_segmented_followup",
                 "activity_selection":"strongest_one_attempt_scan_prior_reacquire_wait12"}
    assert review_continuity(wait,wait_parent,serial=SERIAL,los=LOS)["activity_selection"]==(
        "strongest_one_attempt_scan_prior_reacquire_wait12")
    wait100=prior.replace("continuity30-prior-after-scout1","sparse100-wait12-after-scout1")
    wait100=wait100.replace(" 400000000000\n"," 1200000000000\n",1)
    wait100_parent={**parent,"scope":"bounded_arm_scout_wait100_followup",
                    "rf_sample_limit":837943296,
                    "activity_selection":"strongest_one_attempt_scan_power50_wait12_track100"}
    assert review_continuity(wait100,wait100_parent,serial=SERIAL,los=LOS)["activity_selection"]==(
        "strongest_one_attempt_scan_power50_wait12_track100")
    with pytest.raises(ValueError):
        review_continuity(wait100.replace("candidate 1 0.07","candidate 1 0.049"),
                          wait100_parent,serial=SERIAL,los=LOS)
    wait40=wait100.replace("sparse100-wait12-after-scout1","sparse100-wait40-after-scout1")
    wait40=wait40.replace(" 1200000000000\n"," 1800000000000\n",1)
    wait40_parent={**wait100_parent,
                   "activity_selection":"strongest_one_attempt_scan_power50_wait40_track100"}
    assert review_continuity(wait40,wait40_parent,serial=SERIAL,los=LOS)["activity_selection"]==(
        "strongest_one_attempt_scan_power50_wait40_track100")
    wait40x2=wait40.replace("sparse100-wait40-after-scout1","sparse100-wait40x2-after-scout1")
    wait40x2_parent={**wait40_parent,
                     "activity_selection":"strongest_one_attempt_scan_power50_wait40x2_track100"}
    assert review_continuity(wait40x2,wait40x2_parent,serial=SERIAL,los=LOS)["activity_selection"]==(
        "strongest_one_attempt_scan_power50_wait40x2_track100")


def test_review_accepts_parent_mapping_of_arbitrary_child_failure():
    text,parent=evidence()
    text=text.replace("visit after_run 3 0 ","visit after_run 3 -1 ")
    text=text.replace("segment terminal 1 0","segment terminal 1 -4").replace("terminal 0\n","terminal -4\n")
    parent.update(result=-4,track_complete=0)
    assert review_continuity(text,parent,serial=SERIAL,los=LOS)["status"]=="pass"


def test_persistent_100_second_policy_requires_same_lo_in_consecutive_rounds():
    snapshot=("GLT1SNAP 00010000 474c5431 000a2dfc 00000159 ce8315b0 00000430 "
              "00000002 00000000 00000000 00000000 00000000 00000000 00000000 "
              "00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
              "00000000 01c9c380 00009ab0 b04a2fab 00000001")
    rows=[f"plan 30000000 {SERIAL} {' '.join(map(str,LOS))} "
          "sparse100-wait40x2-confirm2-after-scout1 4 1800000000000"]
    for number in range(9):
        lo=LOS[number%4] if number<8 else LOS[1]
        rows.append("snapshot "+snapshot)
        for kind,latest in (("before_tune",100+number*20),("tuned",101+number*20),
                            ("after_run",110+number*20)):
            epoch=number+2 if kind=="after_run" else number+1
            rows.append(f"visit {kind} {number} 0 {lo} 30000000 {epoch} {latest} 1 1")
        if number in (1,5): rows.append(f"activity candidate {number} 0.07")
        if number==7: rows.append(f"segment start 1 8 1 {LOS[1]} retained_activity")
        if number==8: rows.append("segment terminal 1 0")
    rows.append("terminal 0");text="\n".join(rows)+"\n"
    parent={"scope":"bounded_arm_scout_wait100_followup","rate":30000000,"result":0,
            "rf_sample_limit":938606592,"scan_rounds":2,"segments_started":1,
            "visits_executed":9,"track_complete":1,"selection":"retained_activity",
            "selected_index":1,
            "activity_selection":"strongest_one_attempt_scan_power50_consecutive2_wait40x2_track100"}
    assert review_continuity(text,parent,serial=SERIAL,los=LOS)["status"]=="pass"
    for damaged in (text.replace("activity candidate 1 0.07\n",""),
                    text.replace("activity candidate 1 0.07","activity candidate 1 0.049"),
                    text.replace("activity candidate 1 0.07","activity candidate 1 0.07\nactivity candidate 2 0.08")):
        with pytest.raises(ValueError,match="persistence"):
            review_continuity(damaged,parent,serial=SERIAL,los=LOS)


def test_review_accepts_attested_lo_rounding_within_controller_tolerance():
    text,parent=evidence()
    text="\n".join(line.replace(" 1190312500 30000000"," 1190312498 30000000")
                   if line.startswith("visit ") else line for line in text.splitlines())+"\n"
    assert review_continuity(text,parent,serial=SERIAL,los=LOS)["status"]=="pass"


def test_review_accepts_empty_round_between_ranked_segments():
    text,parent=evidence()
    # Shift the second round's two scouts and follow-up by one complete empty
    # four-LO round, and retain that round as visits 2..5.
    lines=text.splitlines();prefix=[];suffix=[]
    for line in lines:
        if line.startswith("segment start 1 ") or line.startswith("segment terminal 1") or any(
                line.startswith(f"visit {kind} {number} ")
                for kind in ("before_tune","tuned","after_run") for number in (2,3)):
            suffix.append(line)
        else: prefix.append(line)
    terminal=prefix.pop();snapshot=next(line for line in prefix if line.startswith("snapshot "))
    for number,lo in zip(range(2,6),LOS,strict=True):
        prefix.append(snapshot)
        for kind,epoch,latest in (("before_tune",3,300+number*20),("tuned",3,301+number*20),("after_run",4,310+number*20)):
            prefix.append(f"visit {kind} {number} 0 {lo} 30000000 {epoch} {latest} 1 1")
    shifted=[]
    for line in suffix:
        line=line.replace("segment start 1 3 ","segment start 2 7 ").replace("segment terminal 1 ","segment terminal 2 ")
        for kind in ("before_tune","tuned","after_run"):
            line=line.replace(f"visit {kind} 2 ",f"visit {kind} 6 ")
            line=line.replace(f"visit {kind} 3 ",f"visit {kind} 7 ")
        shifted.append(line)
    text="\n".join([*prefix,*shifted,terminal])+"\n"
    parent.update(scan_rounds=3,visits_executed=8,rf_sample_limit=396754944)
    assert review_continuity(text,parent,serial=SERIAL,los=LOS)["visits"]==8
