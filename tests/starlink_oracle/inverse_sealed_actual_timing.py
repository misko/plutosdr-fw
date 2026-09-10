"""Source-specific dual-clock timing ledger; no vendor launch or FFT model.

Clock constants come from the immutable 1ns/1fs actual bench at FAST_MHZ=175.
Fast counters increment on falling edges; slow counters do likewise. Numerical
event verification remains the unchanged independent arithmetic oracle.
"""

import csv
import hashlib
from itertools import pairwise
from pathlib import Path

HISTORICAL_TRACE = "e7127798f315772b95aff63b75fffcd9cf5d1af8ca3c96e878bae4b39e443d71"
FAST_HALF_FS = 2857143
SLOW_PERIOD_FS = 10000000
SLOW_FIRST_FS = 6300000
CANONICAL_PAIR_LIMIT = 5215
NOMINAL_PAIR_LIMIT = 4549 + 8  # planning allocation, not a stalled-delta bound
TRACE_FIELDS = ["cycle", "epoch", "profile", "running", "state", "core_resetn", "admit", "config",
                "inverse", "core_input", "core_output", "status", "guard_commit", "forward_committed",
                "product_commit", "handoff_ack", "result_busy", "source_valid", "source_ready",
                "product_read_valid", "product_read_ready", "output_bank_ready", "fault", "block_start"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_cycles(publication_fast_cycle, profile):
    """Exact request CDC + reader-start + RAM-load then unchanged READY schedule.

    Publication updates request after its fast edge. S1 is the first strictly
    later slow edge. Two synchronizer registers, a reading register and a RAM
    load mean the first possible acceptance is S1+4. The single elastic output
    register holds through stalled READY without inserting a recovery bubble.
    """
    require(type(publication_fast_cycle) is int and publication_fast_cycle >= 0,
            "invalid publication cycle")
    require(type(profile) is int and profile in (0, 1), "invalid READY profile")
    time_fs = FAST_HALF_FS * (2 * publication_fast_cycle + 1)
    first_sample = (time_fs - SLOW_FIRST_FS) // SLOW_PERIOD_FS + 1
    cycle = max(0, first_sample) + 4
    accepted = []
    while len(accepted) < 512:
        if profile == 0 or cycle % 17 < 13:
            accepted.append(cycle)
        cycle += 1
    return accepted


def _completed_epoch(jobs, epoch):
    """Only the immutable full healthy inventory can precede profile reset."""
    owned = [job for job in jobs if job["epoch"] == epoch]
    require(len(owned) == (64 if epoch == 1 else 12), "profile transition before complete epoch")
    for index, job in enumerate(owned):
        require((job["inverse"], job["start"]) ==
                (index % 2, 0x200000000 + epoch * 65536 + (index // 2) * 447),
                "profile transition job identity")
        require(job["config"] == [3] and job["input"] == [5, *range(7, 518)]
                and job["raw"] == list(range(1298, 1810)) and job["status"] == [1300]
                and job["commit"] in ([[1810], [1813]] if job["inverse"] else [[1810]]),
                "profile transition before complete job phases")
    return owned[-1]


def parse_trace(path, transitions=None):
    """Retain all healthy job phases, exact per-beat cycles and source identity."""
    jobs, current, previous = [], None, -1
    transition, transitioned = None, set()
    with Path(path).open() as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == TRACE_FIELDS, "trace schema")
        for raw in reader:
            try:
                cycle, epoch = int(raw["cycle"]), int(raw["epoch"])
            except (ValueError, TypeError) as error:
                raise ValueError("malformed trace row") from error
            require(cycle > previous, "trace cycle regression")
            previous = cycle
            if transition is not None:
                require(cycle == transition["last_cycle"] + 1 and epoch == transition["epoch"],
                        "profile transition must reach adjacent common reset")
                if raw["running"] == "0":
                    try:
                        reset_row = {key: int(value) for key, value in raw.items()}
                    except (ValueError, TypeError) as error:
                        raise ValueError("unknown profile transition reset row") from error
                    require(reset_row["profile"] == transition["next_profile"]
                            and not any(reset_row[name] for name in ("fault", "admit", "config", "core_resetn",
                                "core_input", "core_output", "status", "guard_commit", "result_busy")),
                            "profile transition reset contains active/fault event")
                    transition["reset_cycle"] = cycle
                    if transitions is not None:
                        transitions.append(transition)
                    transitioned.add(epoch)
                    transition = None
            # The full original CSV retains startup unknowns and later deliberate
            # fault epochs. This parser qualifies only the two complete healthy
            # epochs, not arbitrary private fields while common reset is active.
            if epoch not in (1, 2) or raw["running"] == "0":
                current = None
                continue
            try:
                row = {key: int(value) for key, value in raw.items()}
            except (ValueError, TypeError) as error:
                raise ValueError("unknown/malformed healthy running trace row") from error
            require(row["running"] == 1 and row["fault"] == 0, "healthy trace running/fault")
            if row["profile"] != epoch - 1:
                last = _completed_epoch(jobs, epoch)
                require(epoch not in transitioned and row["profile"] == 2 - epoch
                        and row["state"] == 2 and row["inverse"] == 0
                        and row["source_ready"] == row["output_bank_ready"] == 1
                        and row["block_start"] == last["start"]
                        and not any(row[name] for name in ("core_resetn", "admit", "config", "core_input",
                            "core_output", "status", "guard_commit", "forward_committed", "product_commit",
                            "handoff_ack", "result_busy", "source_valid", "product_read_valid", "product_read_ready")),
                        "profile transition is not fully drained WAIT_BANK")
                # The frozen bench sets profile only after await_results, then
                # reset_epoch waits the next slow negedge: <=10 ns, at most two
                # 175-MHz samples. No active job or source is allowed in this
                # interval; its first reset row is checked, not silently skipped.
                if transition is None:
                    transition = {"epoch": epoch, "next_profile": row["profile"],
                                  "first_cycle": cycle, "last_cycle": cycle,
                                  "final_admit": last["admit"], "final_commit": last["admit"] + last["commit"][0]}
                require(cycle - transition["first_cycle"] < 2,
                        "profile transition exceeds frozen next-negedge bound")
                transition["last_cycle"] = cycle
                continue
            require(transition is None and epoch not in transitioned,
                    "profile transition resumed healthy traffic before new epoch")
            if row["admit"]:
                require(current is None or len(current["commit"]) == 1,
                        "repeated admission before prior job commit")
                current = {"epoch": row["epoch"], "inverse": row["inverse"],
                           "start": row["block_start"], "admit": row["cycle"],
                           "config": [], "input": [], "raw": [], "status": [], "commit": []}
                jobs.append(current)
            if current is None:
                require(not any(row[name] for name in
                                ("config", "core_input", "core_output", "status", "guard_commit")),
                        "core event without admitted healthy job")
                continue
            for field, key in (("config", "config"), ("core_input", "input"),
                               ("core_output", "raw"), ("status", "status"),
                               ("guard_commit", "commit")):
                if row[field]:
                    require(row[field] == 1 and row["inverse"] == current["inverse"],
                            "nonbinary event/wrong job phase")
                    current[key].append(row["cycle"] - current["admit"])
    require(transition is None, "truncated profile transition before common reset")
    return jobs


def verify_jobs(jobs, sealed):
    require(type(sealed) is bool, "explicit sealed timing profile required")
    require(len(jobs) == 76, "complete 76-job healthy timing inventory")
    intervals = {1: [], 2: []}
    previous = {}
    for ordinal, job in enumerate(jobs):
        epoch = 1 if ordinal < 64 else 2
        index = ordinal if epoch == 1 else ordinal - 64
        require((job["epoch"], job["inverse"], job["start"])
                == (epoch, index % 2, 0x200000000 + epoch * 65536 + (index // 2) * 447),
                "job phase/source identity")
        expected_commit = 1813 if sealed and job["inverse"] else 1810
        require(job["config"] == [3]
                and job["input"] == [5, *range(7, 518)]
                and job["raw"] == list(range(1298, 1810))
                and job["status"] == [1300]
                and job["commit"] == [expected_commit],
                "immutable generated-core service or declared publication phase changed")
        if not job["inverse"]:
            if epoch in previous:
                interval = job["admit"] - previous[epoch]
                require(0 < interval <= CANONICAL_PAIR_LIMIT, "canonical 5215-cycle pair budget")
                if epoch == 1:
                    require(interval <= (NOMINAL_PAIR_LIMIT if sealed else 4549),
                            "predeclared nominal service allocation")
                intervals[epoch].append(interval)
            previous[epoch] = job["admit"]
    return intervals


def verify_event_cycles(path, jobs):
    """Do not discard timestamps: F/P are FAST, I is SLOW by frozen recorder."""
    owners = {(job["epoch"], job["start"], job["inverse"]): job for job in jobs}
    schedules = {key: read_cycles(job["admit"] + job["commit"][0], key[0] - 1)
                 for key, job in owners.items() if key[2]}
    ledger = {}
    with Path(path).open() as stream:
        for row in csv.DictReader(stream):
            kind = row["stream"]
            require(kind in ("forward", "product", "inverse"), "unknown event clock domain")
            key = int(row["epoch"]), int(row["start"]), int(kind == "inverse")
            require(key in owners, "event without timed job identity")
            job = owners[key]
            position, cycle = int(row["position"]), int(row["cycle"])
            require(0 <= position < 512, "event position range")
            if kind == "inverse":
                expected = schedules[key][position]
            else:
                expected = job["admit"] + (1299 if kind == "forward" else 1304) + position
            require(cycle == expected, "stream-specific absolute event timestamp")
            ledger_key = key[0], kind
            ledger.setdefault(ledger_key, []).append(cycle)
    require(set(ledger) == {(epoch, kind) for epoch in (1, 2)
                            for kind in ("forward", "product", "inverse")},
            "missing stream time ledger")
    for (epoch, _), cycles in ledger.items():
        require(len(cycles) == (32 if epoch == 1 else 6) * 512
                and all(a < b for a, b in pairwise(cycles)),
                "complete strictly ordered stream time ledger")
    return {f"{epoch}_{kind}": {"domain": "slow" if kind == "inverse" else "fast",
                               "count": len(cycles), "first": cycles[0], "last": cycles[-1]}
            for (epoch, kind), cycles in sorted(ledger.items())}


def reader_ack_cycle(last_slow_read):
    """Reader idle is registered one slow edge after final read, then two FFs.

    The fast monitor observes the synchronized value on the following edge,
    matching the pre-NBA observation of the unchanged actual bench.
    """
    idle_time = SLOW_FIRST_FS + (last_slow_read + 1) * SLOW_PERIOD_FS
    first_fast = (idle_time - FAST_HALF_FS) // (2 * FAST_HALF_FS) + 1
    return first_fast + 2


def verify_protocol(path, jobs, inverse_words, ef, ei):
    columns = ["event", "epoch", "fast_cycle", "slow_cycle", "start", "lease", "position", "data", "metadata"]
    with Path(path).open() as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == columns, "protocol event schema")
        rows = list(reader)
    cursor = 0
    previous_fast = -1
    for job in (entry for entry in jobs if entry["inverse"]):
        epoch, start, admit = job["epoch"], job["start"], job["admit"]
        block = (start - 0x200000000 - epoch * 65536) // 447
        fixture, lease = block % 3, block % 4
        metadata = (1 << 74) | (start << 10) | (ef[fixture] << 5) | ei[fixture]
        reads = read_cycles(admit + 1813, epoch - 1)
        ack = reader_ack_cycle(reads[-1])
        expected = [("ADMIT", admit, 0)]
        expected += [("TAKE", admit + 1299 + position, position) for position in range(511)]
        expected += [("QUALIFY", admit + 1810, 511), ("TAKE", admit + 1810, 511),
                     ("CERT", admit + 1811, 511), ("SEAL", admit + 1812, 511),
                     ("PUB", admit + 1813, 511), ("ACK", ack, 511),
                     ("REL", ack + 1, 511), ("REUSE", ack + 2, 511)]
        for event, cycle, position in expected:
            require(cursor < len(rows), "truncated protocol lifetime")
            row = rows[cursor]
            cursor += 1
            try:
                actual = {key: int(value, 16 if key in ("data", "metadata") else 10)
                          for key, value in row.items() if key != "event"}
            except (ValueError, TypeError) as error:
                raise ValueError("malformed protocol row") from error
            slow = max(0, (FAST_HALF_FS * (2 * cycle + 1) - 1300000) // SLOW_PERIOD_FS)
            require(row["event"] == event and actual == {
                "epoch": epoch, "fast_cycle": cycle, "slow_cycle": slow,
                "start": start, "lease": lease, "position": position,
                "data": 0 if event == "ADMIT" else inverse_words[fixture * 512 + position],
                "metadata": 0 if event == "ADMIT" else metadata,
            }, "exact tagged protocol event/data/metadata/dual-clock timing")
            require(cycle >= previous_fast, "protocol fast time regression")
            previous_fast = cycle
    require(cursor == len(rows) and cursor == 38 * 520, "complete protocol receipt inventory")
    return {"lifetimes": 38, "takes": 19456, "ordered_protocol_events": cursor,
            "qualification_to_publication": 3, "ack_to_release": 1}
