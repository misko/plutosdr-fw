"""Invented negative receipts are PARSER ONLY; no RTL/service evidence here."""

import json
import re
from collections import Counter

import pytest

from tests.starlink_oracle.high_rate60_late import (
    ROOT,
    TERMINAL,
    adapt_parser,
    registers,
)
from tests.starlink_oracle.high_rate60_late_result import MARKERS
from tests.starlink_oracle.native60_budget import COHORT, _receipt
from tests.test_starlink_high_rate60_harness_result import paired_specimen, replace
from tests.test_starlink_native60_budget import line


def verify(directory):
    text=(ROOT/"tests/starlink_oracle/high_rate60_harness_result.py").read_text()
    adapted,_=adapt_parser(text)
    scope={"__package__":"tests.starlink_oracle"}
    exec(compile(adapted,"<parser-only late60 context>","exec"),scope)  # noqa: S102 - exact pinned local adapter
    return scope["verify_results"](directory,COHORT)


def late_specimen(directory):
    paired_specimen(directory)
    p=directory/"simulate.log"; log=p.read_text()
    oldoff=_receipt(log,"NATIVE60_SOURCE_OFF",["cycle","source","first","stop","capture","busy"])
    cont=_receipt(log,"HIGH_RATE60_CONTINUOUS",["count","first","stop","first_rise_fs","last_rise_fs","off_fs","startup_pause_outside_segment"])
    clock=_receipt(log,"NATIVE60_CLOCK",["first_edge_fs","first_fall_fs","half_fs","period_fs","control_period_fs","source_edges","after_off_edges","quiet_edges"])
    rise_at=lambda index:cont["first_rise_fs"]+(index-cont["first"])*16666666
    cycle_at=lambda fs:(fs+5000000)//10000000
    trigger=cycle_at(rise_at(34359740288)-8333333); hand=cycle_at(rise_at(34359740336))
    off=oldoff["cycle"]; first_end=hand+208; second_begin=off+8; observation=second_begin+200
    for name in ["native60_actual_raw_tuples.txt","native60_actual_capture.txt","native60_actual_holds.txt"]:
        (directory/name).write_text("")
    records=[r for r in log.splitlines() if not r.startswith(("NATIVE60_","HIGH_RATE60_PASS "))]
    records += [
        "NATIVE60_CONFIG cycle=2700 id=50535354 abi=00010003 rate=60 geometry=0f8c1108 caps=0000001d generation=60000001 eh=1073758594",
        "NATIVE60_LATE_READY cycle=2701 taps=264 generation=60000001 energy=1073758594 engine_idle=1 no_job=1",
        f"NATIVE60_LATE_HANDSHAKE index=34359740336 center=34359740384 capture_first=34359740256 lead=-81 trigger_cycle={trigger} handshake_cycle={hand} request=60000520 generation=60000001 consecutive=1 late=1 duplicate=0 overlap=0 last_admitted=0",
        f"NATIVE60_LATE_LOCAL_REJECT cycle={hand} index=34359740336 rejected=1 late=1 admitted=0 pending=0 capture=0 last_admitted=0",
        f"NATIVE60_LATE_SUBMIT cycle={hand-6} index=34359740332 request=60000520 center=34359740384 timestamp=34359740384",
        line("NATIVE60_SNAPSHOT",{"count":1,"capture_cycle":trigger+2,"return_cycle":trigger+13,
            "captured_index":34359740287,"live_at_capture":34359740289,"public_index":34359740287,
            "retained_index":34359740287,"live_at_return":34359740296,"capture_lag":2,"return_lag":9,
            "maximum_capture_lag":2,"maximum_return_lag":31,"maximum_return_cycles":48}),
        f"NATIVE60_SOURCE_OFF cycle={off} source=16423 first=34359735211 stop=34359751634 capture=0 busy=0",
        f"NATIVE60_LATE_OBSERVATION cycle={observation} public_submit=1 wrapper_handshake=1 fifo_accept=1 sample_handshake=1 rejected=1 late=1 admitted=0 capture=0 raw=0 qualified=0 packet_reads=0 result=0 irq=0 register_reads=62 snapshots=2 source=16425",
        f"NATIVE60_LATE_FINAL observation={observation} source_off={off} quiet_start=99101 quiet_end=99357 maximum_axi=8 sample_checks={clock['source_edges']-((2700*10000000-10433333)//16666666+1)} control_checks=96657 capture=0 raw=0 qualified=0 packet_reads=0 irq=0 result=0",
        line("NATIVE60_CLOCK",clock),
    ]
    for g,begin,end in [(1,hand+8,first_end),(2,second_begin,observation)]:
        records += [f"NATIVE60_LATE_REGISTER generation={g} ordinal={n} address={a:02x} data={v:08x}" for n,(a,v) in enumerate(registers())]
        source=16425 if g==2 else 3113+(end*10000000-cont["first_rise_fs"])//16666666+1
        records += [f"NATIVE60_LATE_AUDIT generation={g} begin_cycle={begin} generation_cycle={begin+50} end_cycle={end} request=60000520 center=34359740384 timestamp=34359740384 last_admitted=0 rejected=1 late=1 admitted=0 register_reads=31 source={source} source_off={g-1} map_retained={g-1} status=00000000"]
    p.write_text("\n".join(records)+"\n"+TERMINAL+"\n")
    replace(directory,"HIGH_RATE60_STOP","native_capture",0); replace(directory,"HIGH_RATE60_STOP","native_busy",0)
    log=p.read_text().replace("map_retained_through_native_release=1 native_result_released=1","map_retained_through_late_observation=1 native_result_created=0")
    log=log.replace("source_at_native_release=","source_at_native_observation=")
    log=log.replace("capture_actual_fft=20 compute_coarse_pilot=300 compute_after_stop=10000","capture_actual_fft=0 compute_coarse_pilot=0 compute_after_stop=0")
    p.write_text(log.replace("source_at_map_release=16425\n","source_at_map_release=16425 fft_after_reject=1024 pilot_after_reject=2000\n"))
    return directory


@pytest.fixture
def synthetic(tmp_path):
    return late_specimen(tmp_path/"PARSER_ONLY_EXPECTED_LATE_NOT_MEASURED")


def test_parser_only_explicit_negative_inventory(synthetic):
    assert json.loads((synthetic/"PARSER_ONLY.json").read_text())["actual_RTL_run"] is False
    r=verify(synthetic)
    assert r["result"]=="HIGH_RATE60_LATE_SIMULATION_VERIFIED"
    assert r["native"]["result"]=="PAIRED60_EXPECTED_LATE_REJECTION_VERIFIED"
    assert sum(MARKERS.values())==74
    assert Counter(re.findall(r"^(NATIVE60_\S+)",(synthetic/"simulate.log").read_text(),re.MULTILINE))==MARKERS


@pytest.mark.parametrize("name",[*MARKERS,"HIGH_RATE60_PASS","HIGH_RATE60_PREFIX","HIGH_RATE60_STOP",
    "HIGH_RATE60_RETENTION_PASS","HIGH_RATE60_PILOT_WORD","HIGH_RATE60_CONTINUOUS","HIGH_RATE60_OVERLAP",
    "HIGH_RATE60_FFT_CLOCK","HIGH_RATE60_PIL1_SNAPSHOT","HIGH_RATE60_PREROLL_PASS"])
@pytest.mark.parametrize("kind",["missing","duplicate"])
def test_missing_duplicate_receipt(synthetic,name,kind):
    p=synthetic/"simulate.log"; records=p.read_text().splitlines(); n=next(i for i,r in enumerate(records) if r.startswith(name+" "))
    if kind=="missing": records.pop(n)
    else: records.append(records[n])
    p.write_text("\n".join(records)+"\n")
    with pytest.raises(ValueError): verify(synthetic)


MUTANTS=[("NATIVE60_CONFIG","rate",30),("NATIVE60_CONFIG","geometry","0f8c1107"),
    ("NATIVE60_LATE_READY","taps",132),("NATIVE60_LATE_READY","no_job",0),("NATIVE60_LATE_READY","engine_idle",0),
    *[("NATIVE60_LATE_HANDSHAKE",k,v) for k,v in [("index",34359740287),("index",34359740449),("lead",-32),("lead",-194),
      ("lead",81),("request","60000521"),("generation","60000002"),("late",0),("consecutive",0),("duplicate",1),("overlap",1),("last_admitted",1)]],
    ("NATIVE60_LATE_LOCAL_REJECT","rejected",0),("NATIVE60_LATE_LOCAL_REJECT","admitted",1),("NATIVE60_LATE_LOCAL_REJECT","capture",1),
    ("NATIVE60_LATE_SUBMIT","request","00000000"),
    *[("NATIVE60_SNAPSHOT",k,v) for k,v in [("public_index",34359740286),("captured_index",34359740290),("retained_index",0),("capture_lag",3),("return_lag",32),("count",0)]],
    ("NATIVE60_SOURCE_OFF","capture",520),("NATIVE60_SOURCE_OFF","busy",1),
    *[("NATIVE60_LATE_OBSERVATION",k,v) for k,v in [("wrapper_handshake",0),("fifo_accept",2),("raw",1),("irq",1),("register_reads",61),("snapshots",1)]],
    *[("NATIVE60_LATE_FINAL",k,v) for k,v in [("control_checks",96656),("sample_checks",1),("maximum_axi",25),("quiet_end",99356)]],
    ("NATIVE60_CLOCK","first_edge_fs",2100000),("NATIVE60_CLOCK","period_fs",14000000),
    ("HIGH_RATE60_STOP","native_capture",1),("HIGH_RATE60_STOP","native_busy",1),
    *[("HIGH_RATE60_OVERLAP",k,v) for k,v in [("capture_actual_fft",1),("fft_after_reject",0),("pilot_after_reject",0),("source_at_native_observation",16424)]],
    ("HIGH_RATE60_RETENTION_PASS","native_result_created",1),
    *[("HIGH_RATE60_PREFIX",k,v) for k,v in [("admitted_scores",893),("forward_input",3585),("continuous",13311),("enabled_raw",14474)]],
    ("HIGH_RATE60_CONTINUOUS","off_fs",0),("HIGH_RATE60_FFT_CLOCK","ideal_clock",0)]


@pytest.mark.parametrize("marker,field,value",MUTANTS)
def test_context_specific_native_coarse_pilot_clock_mutants(synthetic,marker,field,value):
    replace(synthetic,marker,field,value)
    with pytest.raises(ValueError): verify(synthetic)


@pytest.mark.parametrize("field,value",[("generation",1),("request","60000521"),("last_admitted",1),("admitted",1),
    ("rejected",0),("map_retained",0),("source_off",0),("status","00000080"),("source",16424),("begin_cycle",0),
    ("generation_cycle",99999),("end_cycle",99999)])
def test_second_audit_identity_stale_generation_deadline(synthetic,field,value):
    p=synthetic/"simulate.log"; records=p.read_text().splitlines()
    n=next(i for i,r in enumerate(records) if r.startswith("NATIVE60_LATE_AUDIT generation=2 "))
    records[n],count=re.subn(r"\b"+field+r"=[^ ]+",field+"="+str(value),records[n]); assert count==1
    p.write_text("\n".join(records)+"\n")
    with pytest.raises(ValueError): verify(synthetic)


@pytest.mark.parametrize("name",["native60_actual_raw_tuples.txt","native60_actual_capture.txt","native60_actual_holds.txt",
    "native60_actual_source.txt","paired60_actual_prime.txt","paired_pilot_actual.ci16"])
def test_nonempty_native_or_mutated_original_source_pilot(synthetic,name):
    p=synthetic/name; p.write_bytes(p.read_bytes()+b"x")
    with pytest.raises(ValueError): verify(synthetic)


@pytest.mark.parametrize("extra",["FaTaL shutdown","eRrOr escaped","WARNING stale","NATIVE60_ADMISSION fake=1",
    "NATIVE60_RELEASE fake=1","NATIVE60_PACKET_WORD fake=1","HIGH_RATE60_EXTRA fake=1","parser_only"])
def test_failure_shutdown_healthy_native_markers_not_masked(synthetic,extra):
    p=synthetic/"simulate.log"; p.write_text(p.read_text()+extra+"\n")
    with pytest.raises(ValueError): verify(synthetic)


@pytest.mark.parametrize("generation",[1,2])
@pytest.mark.parametrize("ordinal",range(31))
def test_every_public_counter_identity_empty_result_word_exact(synthetic,generation,ordinal):
    p=synthetic/"simulate.log"; records=p.read_text().splitlines()
    prefix=f"NATIVE60_LATE_REGISTER generation={generation} ordinal={ordinal} "
    n=next(i for i,r in enumerate(records) if r.startswith(prefix))
    value=int(records[n].rsplit("=",1)[1],16)^1
    records[n]=records[n].rsplit("=",1)[0]+f"={value:08x}"
    p.write_text("\n".join(records)+"\n")
    with pytest.raises(ValueError): verify(synthetic)


@pytest.mark.parametrize("field",["lead","consecutive","late","last_admitted","index"])
@pytest.mark.parametrize("unknown",["x","z"])
def test_unknown_actual_rejection_protocol_fields_rejected(synthetic,field,unknown):
    replace(synthetic,"NATIVE60_LATE_HANDSHAKE",field,unknown)
    with pytest.raises(ValueError): verify(synthetic)


@pytest.mark.parametrize("name",["native60_actual_raw_tuples.txt","native60_actual_capture.txt","native60_actual_holds.txt"])
def test_missing_empty_log_is_not_zero_native_evidence(synthetic,name):
    # Remove only the generated parser specimen's file, never actual evidence.
    (synthetic/name).unlink()
    with pytest.raises(ValueError): verify(synthetic)
