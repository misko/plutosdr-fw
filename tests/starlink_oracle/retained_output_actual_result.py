"""Strict event/numerical checks; parsing alone never establishes vendor execution."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re

from .retained_output_actual import RECIPE, original, verify_originals


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _fields(line: str) -> dict[str, int]:
    fields = {}
    for token in line.split()[1:]:
        key, value = token.split("=", 1)
        _require(key not in fields and re.fullmatch(r"-?\d+", value) is not None, "receipt token/type")
        fields[key] = int(value)
    return fields


def _packed(word: int, *, signed=False) -> int:
    lo, hi = word & 0x3ffff, (word >> 18) & 0x3ffff
    if signed:
        lo |= 0xfc0000 if lo & 0x20000 else 0
        hi |= 0xfc0000 if hi & 0x20000 else 0
    return (hi << 24) | lo


def _base_receipts(text: str, records: dict) -> dict:
    """Require the inherited exact ownership/phase evidence, not just terminal sums."""
    current = -1
    base = {}
    for line in text.splitlines():
        if line.startswith("RACT_BEGIN "):
            current = _fields(line)["context"]
        if line.startswith("OFFLINE_"):
            name = line.split()[0]
            if name == "OFFLINE_PASS":
                _require(line.startswith("OFFLINE_PASS composition DERIVED_CONTEXT source="), "base context marker")
                line = line.replace("composition DERIVED_CONTEXT ", "", 1)
            if name == "OFFLINE_RESET":
                _require(line.count("aborted_F_input_prefix_at_least64 ") == 1, "reset minimum receipt")
                line = line.replace("aborted_F_input_prefix_at_least64 ", "", 1)
            base.setdefault(name, []).append((current, _fields(line)))
    counts = {"OFFLINE_JOB": 40, "OFFLINE_DISPATCH": 12, "OFFLINE_PUBLICATION": 19,
              "OFFLINE_ACK_CONTROLS": 17, "OFFLINE_REAL_ACK": 17, "OFFLINE_ACK_PHASE": 7,
              "OFFLINE_SERVICE": 7, "OFFLINE_PASS": 7, "OFFLINE_RESET": 2, "OFFLINE_CLOCK": 1}
    _require({k: len(v) for k, v in base.items()} == counts, "base ownership marker inventory")
    for (c, b), a in zip(base["OFFLINE_JOB"], records["RACT_ADMIT"], strict=True):
        _require(c == a["context"] and b == {"phase": a["inverse"], "fixture": (a["start"]-1000)//447, "admit_cycle": a["cycle"]}, "base/actual job join")
    for (c, ack), (c2, real) in zip(base["OFFLINE_ACK_CONTROLS"], base["OFFLINE_REAL_ACK"], strict=True):
        _require(c == c2 and real == {"cycle": ack.get("cycle")} and ack == {"cycle": real["cycle"], "admit": 0, "publication": 0, "transfer": 0}, "known real ACK ownership controls")
    for context in range(7):
        phase = [p for c, p in base["OFFLINE_ACK_PHASE"] if c == context]
        _require(len(phase) == 1 and phase[0]["input"] == 0, "reachable ACK phase classification")
        _require(sum(c == context for c, _ in base["OFFLINE_REAL_ACK"]) == (3 if context < 5 else 1), "complete real ACK count")
        if context == 2:
            _require(phase[0]["parked_full_source"] > 0, "parked complete next source witness")
        if context == 3:
            _require(phase[0]["output"] > 0, "real ACK during F output witness")
        if context == 4:
            _require(phase[0]["handoff"] > 0 and phase[0]["held_final_prefetch"] > 0, "held final ACK witness")
    for c, r in base["OFFLINE_RESET"]:
        _require(c in (5, 6) and r == {"side": c-4, "old_output_unread": 512, "fresh_purge_slow_edges": r.get("fresh_purge_slow_edges")} and r["fresh_purge_slow_edges"] >= 4, "fresh common-epoch reset receipt")
    for _, dispatch in base["OFFLINE_DISPATCH"]:
        _require(set(dispatch) == {"block", "clocks"} and dispatch["clocks"] == 8, "eligible dispatch inventory")
    return base


def verify_result(log: Path, numerical: Path, *, kind: str) -> dict:
    verify_originals()
    _require(kind in ("OFFLINE_SCRIPT_NOT_FFT", "ACTUAL_VENDOR_FFT"), "result kind")
    _require(log.stat().st_size <= 2_000_000 and numerical.stat().st_size <= 20_000_000, "bounded result size")
    text = log.read_text()
    _require(re.search(r"\b(fatal|error)\b", text, re.I) is None, "fatal/error in simulation")
    records = {}
    for line in text.splitlines():
        if line.startswith("RACT_"):
            name = line.split()[0]
            records.setdefault(name, []).append(_fields(line))
    expected_counts = {"RACT_BEGIN": 7, "RACT_CONTEXT": 7, "RACT_ADMIT": 40,
                       "RACT_RESET_RELEASE": 40, "RACT_STATUS": 38, "RACT_JOB": 38,
                       "RACT_SOURCE_ELIGIBILITY": 19, "RACT_ABORT": 2,
                       "RACT_SLOW_PAUSE": 2, "RACT_SLOW_RESUME": 2,
                       "RACT_SHADOW": 1, "RACT_PASS": 1}
    _require({k: len(v) for k, v in records.items()} == expected_counts, "exact marker inventory")
    base = _base_receipts(text, records)
    recipe = json.loads(RECIPE.read_text())
    for i, (start, finish, case) in enumerate(zip(records["RACT_BEGIN"], records["RACT_CONTEXT"], recipe["contexts"], strict=True)):
        _require(start == {"context": i, "stall": case["stall"], "reset": case["reset_side"], "cycle": start.get("cycle")}, "begin identity")
        reset = case["reset_side"] != 0
        fixed = {"context": i, "source": 1536, "F": 3, "I": 2 if reset else 3,
                 "forward": 1024 if reset else 1536, "product": 1024 if reset else 1536,
                 "inverse": 1024 if reset else 1536, "read": 512 if reset else 1536,
                 "status": 4 if reset else 6, "dispatch": 8}
        _require(all(finish.get(k) == v for k, v in fixed.items()), "context inventory")
        _require(set(finish) == set(fixed) | {"service", "publication_interval", "retained_wait", "cycle"}, "context fields")
        _require(0 < finish["cycle"] - start["cycle"] < 1500000 and finish["cycle"] < 1500000, "context/global deadline")
        _require(finish["service"] > 0 and finish["retained_wait"] > 0, "missing service observation")
        if case["stall"] <= 2:
            _require(finish["service"] <= 5215, "absolute service cap")
        if i:
            _require(start["cycle"] > records["RACT_CONTEXT"][i-1]["cycle"], "context chronological order")
    for event in records["RACT_RESET_RELEASE"]:
        _require(set(event) == {"context", "cycle", "sampled_low"} and event["sampled_low"] >= 2, "sampled reset minimum")
    admits = records["RACT_ADMIT"]
    expected_jobs = []
    for context in range(7):
        expected_jobs.extend((context, phase, fixture) for fixture in range(3)
                             for phase in (0, 1) if not (context >= 5 and fixture == 1 and phase == 1))
    jobs = {j["job"]: j for j in records["RACT_JOB"]}
    aborts = {a["job"]: a for a in records["RACT_ABORT"]}
    _require(len(jobs) == 38 and len(aborts) == 2 and not jobs.keys() & aborts.keys(), "unique job lifecycle")
    by_context_fixture = {}
    for number, (admit, (context, phase, fixture)) in enumerate(zip(admits, expected_jobs, strict=True), 1):
        _require(set(admit) == {"context", "job", "inverse", "start", "cycle", "source_valid", "source_start", "retained"}, "admit fields")
        _require((admit["context"], admit["job"], admit["inverse"], admit["start"]) == (context, number, phase, 1000 + fixture*447), "admission identity")
        _require(admit["source_valid"] in (0, 1) and admit["retained"] in (0, 1), "known admission premise")
        if number > 1:
            _require(admit["cycle"] > admits[number-2]["cycle"], "admission chronology")
        if context >= 5 and fixture == 1:
            a = aborts.get(number, {})
            _require(set(a) == {"context", "job", "fixture", "inputs", "first", "last", "raw", "status", "cycle"}, "abort fields")
            _require(a["context"] == context and a["fixture"] == 1 and 64 <= a["inputs"] < 512 and a["raw"] == a["status"] == 0, "aborted exact prefix")
            _require(a["first"] == admit["cycle"]+5 and a["last"]-a["first"]+1 == a["inputs"]+1 and a["cycle"] >= a["last"], "abort timing")
            by_context_fixture[context, phase, fixture] = a["inputs"]
        else:
            j = jobs.get(number, {})
            _require(set(j) == {"context", "job", "inverse", "fixture", "admit", "config_delta", "input_first", "input_last", "raw_first", "publication", "inputs", "raw", "status", "frame"}, "job fields")
            _require((j["context"], j["inverse"], j["fixture"], j["admit"]) == (context, phase, fixture, admit["cycle"]), "job identity")
            _require(j["config_delta"] == 3 and j["inputs"] == j["raw"] == 512 and j["status"] == j["frame"] == 1, "job integration")
            _require(j["input_first"] == j["admit"]+5 and j["input_last"]-j["input_first"]+1 == 513 and j["raw_first"]-j["input_last"] == 781 and j["publication"]-j["admit"] == 1810, "event-indexed absolute service")
            by_context_fixture[context, phase, fixture] = 512
    _require(set(jobs) | set(aborts) == set(range(1, 41)), "all jobs classified")
    event_by_key = {(a["context"], a["inverse"], (a["start"]-1000)//447):
                    jobs.get(a["job"], aborts.get(a["job"])) for a in admits}
    pauses = []
    for context, pause, resume in zip((5, 6), records["RACT_SLOW_PAUSE"], records["RACT_SLOW_RESUME"], strict=True):
        _require(set(pause) == set(resume) == {"context", "slow", "fast", "time_fs"}, "pause/resume fields")
        _require(pause["context"] == resume["context"] == context and pause["slow"] == resume["slow"] and
                 pause["time_fs"] < resume["time_fs"] and pause["fast"] < resume["fast"], "pause/resume chronology")
        _require((pause["time_fs"]-1300000) % 5000000 == 0 and (resume["time_fs"]-1300000) % 5000000 != 0, "pause/resume grid qualification")
        pauses.append((pause["time_fs"], resume["time_fs"]))

    def enabled_ticks(stamp):
        ticks = max(0, (stamp-1300000)//5000000)
        for paused, resumed in pauses:
            if stamp > paused:
                ticks -= max(0, (min(stamp, resumed)-1300000)//5000000 - (paused-1300000)//5000000)
        return ticks

    for pause, resume in zip(records["RACT_SLOW_PAUSE"], records["RACT_SLOW_RESUME"], strict=True):
        for p in (pause, resume):
            _require(p["slow"] == (enabled_ticks(p["time_fs"])+1)//2 and p["fast"] == (p["time_fs"]+2857143)//5714286, "independent pause clock coordinates")
        _require(enabled_ticks(pause["time_fs"]) % 2 == 0, "pause at actual slow falling edge")
        a = next(a for a in aborts.values() if a["context"] == pause["context"])
        sixty_fourth = (2*(a["first"]+64)-1)*2857143
        next_tick = (sixty_fourth-1300000)//5000000+1
        candidates = [t for t in range(next_tick, next_tick+2)
                      if enabled_ticks(1300000+t*5000000) % 2 == 0]
        _require(bool(candidates), "bounded next slow falling edge")
        next_tick = candidates[0]
        _require(pause["time_fs"] == 1300000+next_tick*5000000, "reset stimulus exact next slow fall after64")
        reset_cycle = pause["time_fs"]//5714286+1
        _require(a["cycle"] == a["last"] == reset_cycle and a["inputs"] == a["last"]-a["first"], "exact reset/aborted-prefix coordinate")
    status_ids = set()
    for s in records["RACT_STATUS"]:
        _require(set(s) == {"context", "job", "ordinal", "cycle"} and s["job"] not in status_ids, "status fields/duplicate")
        j = jobs.get(s["job"], {})
        _require(s["context"] == j.get("context") and s["ordinal"] == 2 and s["cycle"] == j.get("raw_first", -4)+2, "status third raw word")
        status_ids.add(s["job"])
    _require(status_ids == set(jobs), "missing status")
    for e in records["RACT_SOURCE_ELIGIBILITY"]:
        _require(set(e) == {"context", "cycle", "source_valid", "source_start"}, "eligibility fields")
        matches = [j for j in jobs.values() if j["inverse"] and j["context"] == e["context"] and j["publication"] == e["cycle"]]
        _require(len(matches) == 1 and e["source_valid"] in (0, 1), "eligibility join")
        fixture = matches[0]["fixture"]
        if fixture < 2:
            _require(e["source_valid"] == 1 and e["source_start"] == 1000+(fixture+1)*447, "next source not already eligible")
            nxt = next(a for a in admits if a["context"] == e["context"] and not a["inverse"] and a["start"] == e["source_start"])
            _require(nxt["cycle"]-e["cycle"] == 8 and nxt["retained"] == 1, "conditional eight-clock dispatch")
    sh = records["RACT_SHADOW"][0]
    _require(set(sh) == {"input_pre", "input_post", "input_resets", "Fstarts", "Istarts", "arithmetic", "retirement"}, "shadow fields")
    _require(sh["input_pre"] == sh["input_post"] and sh["input_pre"] >= 1024 and sh["input_resets"] >= 7 and sh["Fstarts"] == 21 and sh["Istarts"] == 19 and sh["arithmetic"] >= 1024 and sh["retirement"] >= 1024, "complete unconditional shadow receipt")
    terminal = records["RACT_PASS"][0]
    expected_terminal = {"contexts": 7, "source": 10752, "F": 21, "I": 19, "pairs": 19, "aborted_F": 2, "forward": 9728, "product": 9728, "inverse": 9728, "read": 8704, "raw": 19456, "status": 38, "physical_inputs": 19456+sum(a["inputs"] for a in aborts.values()), "discarded_old_unread": 1024}
    _require(terminal == expected_terminal, "terminal inventory")
    vectors = {name: [int(line, 16) for line in (original.BASELINE / f"{name}.mem").read_text().splitlines()]
               for name in ("samples_ci16", "forward_q17", "product_q17", "inverse_q17", "forward_exponents", "inverse_exponents")}
    seen = {}
    stream_times = {}
    previous_stamp = -1
    columns = "context stream job position data start exponent fast slow time_fs".split()
    with numerical.open(newline="") as f:
        reader = csv.DictReader(f)
        _require(reader.fieldnames == columns, "numeric schema")
        for row_index, row in enumerate(reader):
            _require(row_index < 100000 and set(row) == set(columns), "numeric row bound/schema")
            context, fixture, pos = (int(row[k]) for k in ("context", "job", "position"))
            stream = row["stream"]
            _require(0 <= context < 7 and 0 <= fixture < 3 and 0 <= pos < 512, "numeric identity")
            _require(stream in ("source", "inputF", "inputI", "rawF", "rawI", "product", "privateI", "read"), "numeric stream")
            key = context, stream, fixture
            _require(pos == seen.get(key, 0), "duplicate/missing/reordered numerical word")
            seen[key] = pos+1
            source = vectors["samples_ci16"][fixture*447+pos]
            source18 = ((source >> 16) << 20) | ((source & 0xffff) << 2)
            fe, ie = vectors["forward_exponents"][fixture], vectors["inverse_exponents"][fixture]
            if stream in ("source", "inputF"):
                word, exponent = source18, 0
            elif stream in ("inputI", "product"):
                word, exponent = vectors["product_q17"][fixture*512+pos], 0 if stream == "inputI" else fe
            else:
                word = vectors["forward_q17" if stream == "rawF" else "inverse_q17"][fixture*512+pos]
                exponent = fe if stream == "rawF" else ie if stream == "rawI" else (fe << 5) | ie
            expected = _packed(word, signed=stream.startswith("raw")) if stream.startswith(("input", "raw")) else word
            _require(int(row["data"], 16) == expected and int(row["start"], 16) == 1000+fixture*447 and int(row["exponent"], 16) == exponent, "independent numeric payload/packing/metadata")
            fast, slow, stamp = (int(row[k]) for k in ("fast", "slow", "time_fs"))
            _require(fast > 0 and slow > 0 and fast == (stamp+2857143)//5714286, "physical clock coordinate")
            _require(stamp >= previous_stamp, "numerical event chronology")
            previous_stamp = stamp
            _require(slow == (enabled_ticks(stamp)+1)//2, "independent slow edge coordinate")
            _require(records["RACT_BEGIN"][context]["cycle"] <= fast <= records["RACT_CONTEXT"][context]["cycle"], "numeric context interval")
            _require(stamp > stream_times.get(key, -1), "strict per-stream time order")
            stream_times[key] = stamp
            if stream in ("source", "read"):
                _require((stamp-1300000) % 5000000 == 0, "slow edge grid")
            else:
                _require(stamp == (2*fast-1)*2857143, "fast sampled edge")
            if stream.startswith(("input", "raw")):
                e = event_by_key.get((context, int(stream.endswith("I")), fixture))
                _require(e is not None, "unadmitted numeric core owner")
                if stream.startswith("input"):
                    first = e.get("input_first", e.get("first"))
                    _require(fast == first+pos+(pos != 0), "input row/job ordinal time join")
                else:
                    _require("raw_first" in e and fast == e["raw_first"]+pos, "raw row/job ordinal time join")
            if stream == "privateI":
                _require(fast == event_by_key[context, 1, fixture]["raw_first"]+pos+1, "private row/job retirement time join")
            if stream == "product":
                forward = event_by_key[context, 0, fixture]
                inverse = event_by_key[context, 1, fixture]
                _require(forward["raw_first"] < fast < inverse["admit"], "product between forward return and inverse admission")
            if stream == "read":
                inverse = event_by_key[context, 1, fixture]
                ack = [r for c, r in base["OFFLINE_REAL_ACK"] if c == context][fixture if context < 5 else 0]
                _require((2*inverse["publication"]-1)*2857143 < stamp < (2*ack["cycle"]-1)*2857143, "read between own publication and real ACK")
    expected_seen = {}
    for context in range(7):
        for fixture in range(3):
            expected_seen[context, "source", fixture] = 512
            for phase, stream in ((0, "inputF"), (1, "inputI")):
                if (context, phase, fixture) in by_context_fixture:
                    expected_seen[context, stream, fixture] = by_context_fixture[context, phase, fixture]
            if context >= 5 and fixture == 1:
                continue
            for stream in ("rawF", "rawI", "product", "privateI"):
                expected_seen[context, stream, fixture] = 512
            if context < 5 or fixture == 2:
                expected_seen[context, "read", fixture] = 512
    _require(seen == expected_seen, "complete independent numerical stream inventory")
    for context in range(7):
        for fixture in range(3):
            admit = next(a for a in admits if a["context"] == context and a["inverse"] == 0 and a["start"] == 1000+447*fixture)
            _require(stream_times[context, "source", fixture] < (2*admit["cycle"]-1)*2857143, "complete source precedes forward admission")
    _require("OFFLINE_CLOCK fast_half_fs=2857143 slow_half_fs=5000000" in text, "actual clock witness missing")
    return {"kind": kind, "parser_only_not_execution_proof": True, "terminal": terminal,
            "contexts": records["RACT_CONTEXT"], "aborts": records["RACT_ABORT"],
            "numerical_words": sum(seen.values())}
