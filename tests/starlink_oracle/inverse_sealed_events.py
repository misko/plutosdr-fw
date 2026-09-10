"""Independent accepted-event model and Icarus continuous-node graph checks.

No FFT model or production-state transition copy. This consumes the public
transaction receipts of the bounded nonzero guard composition, and treats
slow-prefix acceptance before sticky-fault visibility as provisional.
"""

import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def golden_word(job, position):
    return (((job + 1) * 0x123450001 + position * 0x10203) ^ (position << 19)) & (
        (1 << 36) - 1
    )


def golden_metadata(job):
    return (1 << 74) | ((0x200000001 + job * 447) << 10) | (7 << 5) | 9


EVENTS = {
    "ADMIT": r"ADMIT (\d+) (\d+) (\d+) lease=(\d+)",
    "TAKE": r"TAKE (\d+) (\d+) (\d+) (\d+) ([0-9a-f]+) ([0-9a-f]+) lease=(\d+)",
    "CERT": r"CERT (\d+) (\d+) (\d+)",
    "PUB": r"PUB (\d+) (\d+) (\d+) original=(-?\d+) first_qualified=(-?\d+)",
    "ACK": r"ACK (\d+) (\d+) (\d+)",
    "RELEASE": r"RELEASE (\d+) (\d+) (\d+) ack=(-?\d+) final_slow=(-?\d+)",
    "OUT": r"OUT (\d+) (\d+) (\d+) mode=([01]) pos=(\d+) data=([0-9a-f]+) metadata=([0-9a-f]+)",
    "CAUSE": r"CAUSE (\d+) (\d+) ([0-9a-f]+)",
    "S1": r"S1 (\d+) reads=(\d+)",
    "LIFECYCLE": r"LIFECYCLE job=(\d+) publication_delta=(\d+) ack_to_release=(\d+) reuse_delta=(\d+) takes=(\d+)",
    "RESET_STAGE": r"RESET_STAGE phase=(\d+) takes=(\d+) certs=(\d+) pubs=(\d+) reads=(\d+) ack=([01])",
    "RESET_REARM": r"RESET_REARM epoch=(\d+) phase=(\d+) side=([01])",
    "METADATA_REJECT": r"METADATA_REJECT bit=(\d+) offered=(\d+) fault_position=(\d+) lease=(\d+)",
}


def verify_guard_events(log, case, phase=0, bit=0, side=0):
    """Check every nonzero token, lease, epoch, event ordering and case receipt.

    External current faults need not be observed instantaneously in the slow
    domain. Only S1 is the pre-edge sampling anchor for the exact S3 cutoff.
    """
    require(case in range(13), "unknown profile")
    require(not re.search(r"(?i)\b(?:fatal|error|fail)\b", log), "failed simulation")
    terminal = (
        f"INVERSE_GUARD_OFFLINE_PASS case={case} phase_ps={phase} synthetic_not_fft=1"
    )
    lines = log.splitlines()
    require(lines and lines[-1] == terminal and lines.count(terminal) == 1, "terminal")
    jobs, active, epoch, lease, fast, slow = [], None, 1, 0, -1, -1
    evidence = {}
    expected_literals = {
        2: "DEADLINE_VETO qualified_certificate_held=1 original_publications=1",
        4: "PROVISIONAL_PREFIX count=19 healthy=0 releases=0",
        5: "PROVISIONAL_PREFIX count=512 healthy=0 releases=0",
        6: "PENDING_REQUEST_FAULT_PREFIX count=0",
        11: "FIRST_FINAL_SLOW_STALL first_cycles=23 final_cycles=29",
        12: "RELEASE_EDGE_CURRENT_VETO reads=512 release=0 reusable=0",
    }
    for line in lines[:-1]:
        if line == expected_literals.get(case):
            require("literal" not in evidence, "duplicate case receipt")
            evidence["literal"] = line
            continue
        kind = line.split(" ", 1)[0]
        match = re.fullmatch(EVENTS.get(kind, r"(?!)"), line)
        require(match is not None, "unknown/malformed receipt: " + line)
        fields = match.groups()
        if kind in ("ADMIT", "TAKE", "CERT", "PUB", "ACK", "RELEASE", "CAUSE"):
            cycle, tag_epoch = map(int, fields[:2])
            require(cycle >= fast and tag_epoch == epoch, "fast cycle/epoch")
            fast = cycle
        if kind == "ADMIT":
            job, offered_lease = map(int, fields[2:])
            require(
                active is None and job == len(jobs) and offered_lease == lease,
                "admission ownership",
            )
            active = {
                "job": job,
                "epoch": epoch,
                "lease": lease,
                "takes": 0,
                "cert": [],
                "pub": [],
                "ack": [],
                "release": [],
                "reads": [0, 0],
                "causes": 0,
                "last_take": -1,
                "s1": None,
            }
            jobs.append(active)
        elif kind == "RESET_STAGE":
            values = tuple(map(int, fields))
            expected = [0, 17, 512, 512, 512, 512, 512][bit]
            require(
                case == 10 and active is not None and "reset" not in evidence,
                "unexpected reset",
            )
            require(
                values[:5]
                == (
                    bit,
                    expected,
                    int(bit >= 4),
                    int(bit >= 4),
                    [0, 0, 0, 0, 0, 17, 512][bit],
                ),
                "reset stimulus inventory",
            )
            require(
                values[1:5]
                == (
                    active["takes"],
                    len(active["cert"]),
                    len(active["pub"]),
                    active["reads"][1],
                ),
                "reset event counts",
            )
            evidence["reset"] = values
            active = None
        elif kind == "RESET_REARM":
            require(
                case == 10
                and active is None
                and "reset" in evidence
                and "rearm" not in evidence,
                "unwitnessed rearm",
            )
            require(tuple(map(int, fields)) == (2, bit, side), "rearm identity")
            epoch, lease = 2, 0
            evidence["rearm"] = True
        elif kind == "LIFECYCLE":
            job, pub_delta, ack_delta, reuse_delta, takes = map(int, fields)
            owner = jobs[job] if job < len(jobs) else None
            require(
                owner is not None
                and len(owner["release"]) == 1
                and takes == owner["takes"] == 512,
                "lifecycle without release",
            )
            require(
                pub_delta == 2
                and ack_delta == owner["release"][0] - owner["ack"][0] == 1
                and 0 <= reuse_delta <= 8,
                "lifecycle timing",
            )
            require("lifecycle" not in owner, "duplicate lifecycle")
            owner["lifecycle"] = reuse_delta
        elif kind == "METADATA_REJECT":
            require(
                case in (7, 8, 9) and "metadata" not in evidence,
                "unexpected metadata rejection",
            )
            offered, fault = (
                (0, 1) if case == 7 else (17, 17) if case == 8 else (511, 511)
            )
            require(
                tuple(map(int, fields)) == (bit, offered, fault, 0),
                "metadata original token identity",
            )
            require(
                active is not None and active["causes"] & 8,
                "metadata rejection without actual cause",
            )
            evidence["metadata"] = True
        else:
            require(active is not None, "event without owned job")
            if kind in ("TAKE", "CERT", "PUB", "ACK", "RELEASE", "OUT"):
                require(
                    int(fields[2]) == active["job"]
                    and int(fields[1]) == active["epoch"],
                    "event job/epoch",
                )
            if kind == "TAKE":
                position, data, metadata, offered_lease = (
                    int(fields[3]),
                    int(fields[4], 16),
                    int(fields[5], 16),
                    int(fields[6]),
                )
                require(
                    position == active["takes"] < 512 and not active["pub"],
                    "private token order",
                )
                require(
                    offered_lease == active["lease"]
                    and data == golden_word(active["job"], position),
                    "private data/lease",
                )
                expected = golden_metadata(active["job"])
                if case in (7, 8, 9) and position == {7: 0, 8: 17, 9: 511}[case]:
                    expected ^= 1 << bit
                require(
                    metadata == expected and fast > active["last_take"],
                    "private metadata/cycle",
                )
                active["takes"] += 1
                active["last_take"] = fast
            elif kind == "CERT":
                require(
                    active["takes"] == 512
                    and not active["cert"]
                    and fast > active["last_take"],
                    "certificate before payload/duplicate",
                )
                active["cert"].append(fast)
            elif kind == "PUB":
                require(
                    active["takes"] == 512
                    and len(active["cert"]) == 1
                    and not active["pub"]
                    and not active["causes"],
                    "unqualified publication",
                )
                require(
                    fast > active["cert"][0] and fast >= active["last_take"] + 3,
                    "publication before check drain",
                )
                require(
                    fast - int(fields[3]) == fast - int(fields[4]) == 2,
                    "publication latency",
                )
                active["pub"].append(fast)
            elif kind == "OUT":
                output_cycle, mode, position, data, metadata = (
                    int(fields[0]),
                    int(fields[3]),
                    int(fields[4]),
                    int(fields[5], 16),
                    int(fields[6], 16),
                )
                require(output_cycle >= slow, "slow event cycle order")
                slow = output_cycle
                require(
                    position == active["reads"][mode] < 512
                    and data == golden_word(active["job"], position)
                    and metadata == golden_metadata(active["job"]),
                    "output data/metadata/ordinal",
                )
                if mode == 1:
                    require(
                        len(active["pub"]) == 1
                        and (active["s1"] is None or output_cycle < active["s1"] + 2),
                        "unpublished/late fault output",
                    )
                active["reads"][mode] += 1
            elif kind == "CAUSE":
                reason = int(fields[2], 16)
                require(reason | active["causes"] == reason, "nonsticky cause")
                active["causes"] = reason
            elif kind == "S1":
                cycle, count = map(int, fields)
                require(
                    active["s1"] is None
                    and count == active["reads"][1]
                    and cycle >= slow,
                    "slow fault sample anchor",
                )
                active["s1"] = cycle
                slow = cycle
            elif kind == "ACK":
                require(
                    len(active["pub"]) == 1
                    and active["reads"][1] == 512
                    and not active["ack"],
                    "ACK before final read/duplicate",
                )
                active["ack"].append(fast)
            elif kind == "RELEASE":
                require(
                    len(active["ack"]) == 1
                    and not active["release"]
                    and not active["causes"]
                    and int(fields[3]) == active["ack"][0] < fast,
                    "release without healthy drained ACK",
                )
                active["release"].append(fast)
                active = None
                lease = (lease + 1) % 4
    require(len(jobs) == (2 if case in (0, 1, 10) else 1), "missing jobs/stimulus")
    if case in expected_literals:
        require("literal" in evidence, "missing bounded case receipt")
    if case in (7, 8, 9):
        require("metadata" in evidence, "missing metadata stimulus")
    if case == 10:
        require("reset" in evidence and "rearm" in evidence, "missing reset/rearm")
    for owner in jobs:
        healthy = case in (0, 1, 11) or (case == 10 and owner["epoch"] == 2)
        if healthy:
            require(
                owner["takes"] == 512
                and owner["reads"] == [512, 512]
                and len(owner["release"]) == 1
                and "lifecycle" in owner
                and owner["causes"] == 0,
                "incomplete healthy lifecycle",
            )
        elif case != 10:
            takes = {7: 2, 8: 18}.get(case, 512)
            reads = {4: 19, 5: 512, 12: 512}.get(case, 0)
            require(
                owner["takes"] == takes
                and owner["reads"][1] == reads
                and not owner["release"]
                and owner["causes"] != 0,
                "incomplete negative stimulus/fault inventory",
            )
            require(
                len(owner["cert"]) == int(case < 7 or case == 12)
                and len(owner["pub"]) == int(case in (4, 5, 6, 12))
                and len(owner["ack"]) == int(case in (5, 12)),
                "negative join inventory",
            )
            if case in (4, 5, 6):
                require(owner["s1"] is not None, "missing slow fault sample anchor")
    return {
        "jobs": len(jobs),
        "takes": sum(j["takes"] for j in jobs),
        "candidate_outputs": sum(j["reads"][1] for j in jobs),
        "healthy_releases": sum(len(j["release"]) for j in jobs),
    }


def continuous_graph(vvp):
    """Icarus continuous nodes/net aliases only; procedural state is a cut.

    This is an elaboration graph check, NOT synthesis, Boolean reachability or
    physical timing. Array/packed nodes are conservative whole-vector nodes.
    """
    graph, operations = {}, set()
    references = r"(?:LS?_0x[0-9a-f]+(?:_\d+)*|v0x[0-9a-f]+(?:_\d+)?)"
    for line in vvp.splitlines():
        match = re.match(r"^(LS?_\S+) (\.\S+) (.*);", line)
        if match:
            node, operation, body = match.groups()
            operations.add(operation)
            graph[node] = set(re.findall(references, body))
        match = re.match(r"^(v\S+) \.net (.*);", line)
        if match:
            node, body = match.groups()
            graph[node] = set(re.findall(references, body))
    require(len(graph) > 100, "missing elaborated continuous graph")
    require(
        all(
            child in graph
            for children in graph.values()
            for child in children
            if child.startswith("L")
        ),
        "unresolved continuous node",
    )
    visited, pending = set(), set()

    def visit(node, stack):
        if node in pending:
            raise ValueError(
                "combinational cycle: "
                + " -> ".join(stack[stack.index(node) :] + [node])
            )
        if node in visited or node not in graph:
            return
        pending.add(node)
        for child in graph[node]:
            visit(child, stack + [node])
        pending.remove(node)
        visited.add(node)

    for node in graph:
        visit(node, [])
    return {"nodes": len(graph), "operations": sorted(operations), "cyclic": False}
