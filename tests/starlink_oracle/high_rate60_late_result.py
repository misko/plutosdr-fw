"""Strict negative-native receipt gate; no invented admission/result evidence."""

import re
from collections import Counter

from .high_rate60_late import check_recipe, registers
from .native60_budget import _receipt, check_cohort, require, verify_snapshot

MARKERS = {name: 1 for name in ["NATIVE60_CONFIG", "NATIVE60_SNAPSHOT", "NATIVE60_SOURCE_OFF",
    "NATIVE60_CLOCK", "NATIVE60_LATE_READY", "NATIVE60_LATE_HANDSHAKE", "NATIVE60_LATE_LOCAL_REJECT",
    "NATIVE60_LATE_SUBMIT", "NATIVE60_LATE_OBSERVATION", "NATIVE60_LATE_FINAL"]} | {
        "NATIVE60_LATE_REGISTER": 62, "NATIVE60_LATE_AUDIT": 2}


def signed_receipt(log, name, fields, hex_fields=()):
    """Only lead may be signed. Preserve actual negative evidence, no log edit."""
    records = re.findall(r"^"+name+r" (.*)$",log,re.MULTILINE)
    require(len(records) == 1, f"missing/duplicate {name}")
    pairs = [word.split("=") for word in records[0].split()]
    require(len(pairs) == len(fields) and all(len(pair) == 2 for pair in pairs) and
            {pair[0] for pair in pairs} == set(fields), f"unexpected fields {name}")
    out = {}
    for key,value in pairs:
        pattern = r"[0-9a-f]+" if key in hex_fields else (r"-?[0-9]+" if key == "lead" else r"[0-9]+")
        require(re.fullmatch(pattern,value) is not None, f"unknown/noninteger {name}")
        out[key] = int(value,16 if key in hex_fields else 10)
    return out


def verify_native_component(directory, inputs, log):
    r = check_recipe()
    check_cohort(inputs)
    require(not re.search(r"(?i)\b(?:fail(?:ed|ure)?|fatal|error|warning)\b|parser_only",log), "late failure/nonservice log")
    for name in ["native60_actual_raw_tuples.txt","native60_actual_capture.txt","native60_actual_holds.txt"]:
        path = directory/name
        require(path.is_file() and path.stat().st_size == 0, "late native raw/capture/hold log not empty")
    path = directory/"native60_actual_source.txt"
    require(path.is_file() and path.stat().st_size < 10_000_000, "late source log missing/oversized")
    indexes = (inputs/"source_index_u64.mem").read_text().splitlines()
    source_iq = (inputs/"source_ci16.mem").read_text().splitlines()
    require(path.read_text().splitlines() == [f"{i} {v}" for i,v in zip(indexes,source_iq,strict=True)],
            "late unchanged all16423 source/index/packing")
    cfg = _receipt(log,"NATIVE60_CONFIG",["cycle","id","abi","rate","geometry","caps","generation","eh"],
                   {"id","abi","geometry","caps","generation"})
    require([cfg[k] for k in ["id","abi","rate","geometry","caps","generation","eh"]] ==
            [0x50535354,0x10003,60,0x0f8c1108,0x1d,0x60000001,1073758594], "late public native60 configuration identity")
    ready = _receipt(log,"NATIVE60_LATE_READY",["cycle","taps","generation","energy","engine_idle","no_job"],{"generation"})
    require([ready[k] for k in ["taps","generation","energy","engine_idle","no_job"]] ==
            [264,0x60000001,1073758594,1,1] and cfg["cycle"] <= ready["cycle"] <= cfg["cycle"]+1,
            "late explicit coefficient-ready/idle witness")
    adm = signed_receipt(log,"NATIVE60_LATE_HANDSHAKE",["index","center","capture_first","lead","trigger_cycle",
        "handshake_cycle","request","generation","consecutive","late","duplicate","overlap","last_admitted"],{"request","generation"})
    require(34359740288 <= adm["index"] <= 34359740448 and adm["center"] == 34359740384 and
            adm["capture_first"] == 34359740256 and adm["lead"] == 34359740256-adm["index"]-1 and
            -193 <= adm["lead"] <= -33 and adm["request"] == 0x60000520 and adm["generation"] == 0x60000001 and
            [adm[k] for k in ["consecutive","late","duplicate","overlap","last_admitted"]] == [1,1,0,0,0] and
            ready["cycle"] < adm["trigger_cycle"] <= adm["handshake_cycle"] <= adm["trigger_cycle"]+256,
            "late actual command identity/consecutive-coordinate/signed lead/deadline")
    local = _receipt(log,"NATIVE60_LATE_LOCAL_REJECT",["cycle","index","rejected","late","admitted","pending","capture","last_admitted"])
    require(local == {"cycle":adm["handshake_cycle"],"index":adm["index"],"rejected":1,"late":1,
                     "admitted":0,"pending":0,"capture":0,"last_admitted":0}, "late physical same-edge rejection evidence")
    submit = _receipt(log,"NATIVE60_LATE_SUBMIT",["cycle","index","request","center","timestamp"],{"request"})
    require(adm["trigger_cycle"] <= submit["cycle"] <= adm["handshake_cycle"] and
            34359740288 <= submit["index"] <= adm["index"] and submit["request"] == 0x60000520 and
            submit["center"] == submit["timestamp"] == 34359740384, "late public submit identity/order")
    snap = _receipt(log,"NATIVE60_SNAPSHOT",["count","capture_cycle","return_cycle","captured_index","live_at_capture",
        "public_index","retained_index","live_at_return","capture_lag","return_lag","maximum_capture_lag",
        "maximum_return_lag","maximum_return_cycles"])
    verify_snapshot(snap,adm["trigger_cycle"],submit["cycle"])
    off = _receipt(log,"NATIVE60_SOURCE_OFF",["cycle","source","first","stop","capture","busy"])
    require({k:off[k] for k in off if k != "cycle"} ==
            {"source":16423,"first":34359735211,"stop":34359751634,"capture":0,"busy":0}, "late full-source empty native stop")
    observed = _receipt(log,"NATIVE60_LATE_OBSERVATION",["cycle","public_submit","wrapper_handshake","fifo_accept",
        "sample_handshake","rejected","late","admitted","capture","raw","qualified","packet_reads","result","irq",
        "register_reads","snapshots","source"])
    expected = {k:0 for k in ["admitted","capture","raw","qualified","packet_reads","result","irq"]}
    expected |= {k:1 for k in ["public_submit","wrapper_handshake","fifo_accept","sample_handshake","rejected","late"]}
    expected |= {"register_reads":62,"snapshots":2,"source":16425}
    require({k:observed[k] for k in observed if k != "cycle"} == expected and
            adm["handshake_cycle"] < off["cycle"] < observed["cycle"] <= off["cycle"]+2048,
            "late bounded full-source zero-work observation")
    audit_lines = re.findall(r"^NATIVE60_LATE_AUDIT .*$",log,re.MULTILINE)
    require(len(audit_lines) == 2, "late snapshot audit multiplicity")
    audits = [_receipt(line,"NATIVE60_LATE_AUDIT",["generation","begin_cycle","generation_cycle","end_cycle","request",
        "center","timestamp","last_admitted","rejected","late","admitted","register_reads","source","source_off",
        "map_retained","status"],{"request","status"}) for line in audit_lines]
    for generation,a in enumerate(audits,1):
        require(a["generation"] == generation and a["request"] == 0x60000520 and
                a["center"] == a["timestamp"] == 34359740384 and a["last_admitted"] == a["admitted"] == 0 and
                a["rejected"] == a["late"] == 1 and a["register_reads"] == 31 and a["status"] & 0xc0 == 0 and
                adm["handshake_cycle"]+8 <= a["begin_cycle"] <= a["generation_cycle"] <= a["begin_cycle"]+512 and
                a["generation_cycle"] <= a["end_cycle"] <= a["begin_cycle"]+1328 and
                a["source_off"] in [0,1] and a["map_retained"] in [0,1], "late public audit identity/zero-state/deadline")
    require(audits[0]["end_cycle"] < off["cycle"] and audits[0]["source_off"] == 0 and
            3113 < audits[0]["source"] < 16425 and
            off["cycle"]+8 <= audits[1]["begin_cycle"] and audits[1]["source"] == 16425 and
            audits[1]["source_off"] == audits[1]["map_retained"] == 1 and audits[1]["end_cycle"] == observed["cycle"],
            "late two unique audits across full source with retained map")
    actual = re.findall(r"^NATIVE60_LATE_REGISTER generation=(\d+) ordinal=(\d+) address=([0-9a-f]{2}) data=([0-9a-f]{8})$",log,re.MULTILINE)
    require(actual == [(str(g),str(n),f"{address:02x}",f"{value:08x}") for g in [1,2]
                       for n,(address,value) in enumerate(registers())], "late all62 public counter registers")
    b = _receipt(log,"NATIVE60_LATE_FINAL",["observation","source_off","quiet_start","quiet_end","maximum_axi",
        "sample_checks","control_checks","capture","raw","qualified","packet_reads","irq","result"])
    require(b["observation"] == observed["cycle"] and b["source_off"] == off["cycle"] and
            b["observation"] <= b["quiet_start"] and b["quiet_end"]-b["quiet_start"] == 256 and
            b["quiet_end"] < r["global_control_watchdog"] and 1 <= b["maximum_axi"] <= 24 and
            all(b[k] == 0 for k in ["capture","raw","qualified","packet_reads","irq","result"]),
            "late final no-stale/zero-work/global budget")
    clock = _receipt(log,"NATIVE60_CLOCK",["first_edge_fs","first_fall_fs","half_fs","period_fs","control_period_fs",
        "source_edges","after_off_edges","quiet_edges"])
    for key,value in {"first_edge_fs":10433333,"first_fall_fs":18766666,"half_fs":8333333,
                       "period_fs":16666666,"control_period_fs":10000000}.items():
        require(abs(clock[key]-value) <= 1, "late actual source oscillator origin/cadence")
    edges_at = lambda cycle: (cycle*10000000-10433333)//16666666+1
    require(clock["source_edges"] == edges_at(b["quiet_end"]) and
            clock["quiet_edges"] == edges_at(b["quiet_end"])-edges_at(b["quiet_start"]) and
            152 <= clock["quiet_edges"] <= 155 and clock["quiet_edges"] <= clock["after_off_edges"] <= clock["source_edges"] and
            b["sample_checks"] == clock["source_edges"]-edges_at(cfg["cycle"]) and
            b["control_checks"] == b["quiet_end"]-cfg["cycle"], "late continuing clock/complete post-ready state observation")
    off_time = 18766666+(clock["source_edges"]-clock["after_off_edges"]-1)*16666666
    require(b["source_off"]*10000000-5000000 <= off_time < b["source_off"]*10000000+5000000,
            "late source-off falling edge/control coordinate")
    require(Counter(re.findall(r"^(NATIVE60_\S+)",log,re.MULTILINE)) == MARKERS, "late native marker inventory")
    return {"result":"PAIRED60_EXPECTED_LATE_REJECTION_VERIFIED","budget":b,"clock":clock,"rejection":adm,
            "snapshot":snap,"audits":audits,"observation":observed,
            "scope":"native expected expiry, no admitted capture/compute/result; not healthy native service"}
