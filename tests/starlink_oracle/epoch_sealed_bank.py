"""Independent transaction/event checks for the offline sealed-bank prototype."""

import re


class FiniteIssuer:
    """Executable *interface assumption* model, not another bank RTL model.

    Each source/status actor can retain one old and one future reference. Taking
    a token does not erase its issuer reference: an explicit consumption ACK is
    necessary. Reset invalidates ownership but cannot erase a peer's queue.
    ``epoch`` is model bookkeeping, not extra transmitted hardware identity.
    """

    peers = ("producer", "certificate", "consumer")

    def __init__(self):
        self.epoch = 0
        self.lease = 0
        self.active = False
        self.refs = {peer: {} for peer in self.peers}
        self.flush_ack = set()

    def reset(self):
        self.epoch += 1
        self.lease = 0
        self.active = False
        self.flush_ack.clear()

    def flush(self, peer):
        self.refs[peer].clear()
        self.flush_ack.add(peer)

    def rearm(self, engine_reset_held):
        if (
            self.active
            or not engine_reset_held
            or self.flush_ack != set(self.peers)
            or any(self.refs.values())
        ):
            raise ValueError("reset/peer drain incomplete")
        self.active = True

    def enqueue(self, peer, identity, lease):
        queue = self.refs[peer]
        if (
            not self.active
            or identity in queue
            or len(queue) == 2
            or lease not in (self.lease, (self.lease + 1) % 4)
        ):
            raise ValueError("unowned/duplicate/full/nonadjacent issuer reference")
        queue[identity] = (self.epoch, lease, "queued")

    def consume(self, peer, identity):
        epoch, lease, state = self.refs[peer][identity]
        if (
            not self.active
            or (epoch, lease) != (self.epoch, self.lease)
            or state != "queued"
        ):
            raise ValueError("duplicate/stale/future reference cannot be consumed")
        self.refs[peer][identity] = (epoch, lease, "consumed")

    def acknowledge_consumption(self, peer, identity):
        if self.refs[peer][identity][2] != "consumed":
            raise ValueError("acknowledgement before actual consumption")
        del self.refs[peer][identity]

    def release(self, tag, reader_ack, local_pipe_empty):
        if (
            not self.active
            or tag != self.lease
            or not reader_ack
            or not local_pipe_empty
            or any(
                (epoch, lease) == (self.epoch, self.lease)
                for queue in self.refs.values()
                for epoch, lease, _ in queue.values()
            )
        ):
            raise ValueError("old ownership still referenced or wrong release")
        self.lease = (self.lease + 1) % 4


def golden_metadata(job):
    return (1 << 74) | ((0x200000001 + job * 447) << 10) | (7 << 5) | 9


def golden_word(job, position):
    return (((job + 1) * 0x123450001 + position * 0x10203) ^ (position << 19)) & (
        (1 << 36) - 1
    )


def verify_events(log, case, bit=0, phase=0):
    """No candidate predicates/state are used as the expected token or deadline."""
    if re.search(r"(?i)\b(fatal|error|fail)\b", log):
        raise ValueError("failed simulation")
    terminals = re.findall(
        r"^SEALED_BANK_PASS case=(\d+) bit=(\d+) phase=(\d+) cycles=(\d+)$",
        log,
        re.MULTILINE,
    )
    if len(terminals) != 1 or tuple(map(int, terminals[0][:3])) != (case, bit, phase):
        raise ValueError("missing/duplicate/wrong terminal")
    if not log.strip().splitlines()[-1].startswith("SEALED_BANK_PASS "):
        raise ValueError("events after terminal")
    bank = None
    completed = 0
    published = 0
    words = 0
    seals = 0
    lease_history = []
    previous_cycle = -1
    counts = {
        event: 0
        for event in (
            "RESET",
            "JOB",
            "TAKE",
            "CERT",
            "SEAL",
            "PUB",
            "OUT",
            "REL",
            "TWO_EDGE_FAULT",
        )
    }
    fault_union = 0
    jobs = []
    for line in log.splitlines():
        parts = line.split()
        if not parts:
            continue
        kind = parts[0]
        if kind in counts:
            counts[kind] += 1
        if kind in (
            "RESET",
            "JOB",
            "TAKE",
            "CERT",
            "SEAL",
            "PUB",
            "OUT",
            "REL",
            "FAULT",
        ):
            if int(parts[1]) < previous_cycle:
                raise ValueError("event cycle moved backwards")
            previous_cycle = int(parts[1])
        if kind == "RESET":
            bank = None
        elif kind == "JOB":
            _, cycle, epoch, lease, job, metadata = parts
            if bank is not None:
                raise ValueError("bank overwritten before release/reset")
            bank = {
                "epoch": int(epoch),
                "lease": int(lease),
                "job": int(job),
                "take": [],
                "read": 0,
                "certificate": False,
                "certificate_consumed": False,
                "sealed": False,
                "published": False,
                "poison": False,
                "fault": False,
                "local_bad": False,
                "first_metadata": None,
                "first_bad_token": None,
            }
            if int(metadata, 16) != golden_metadata(int(job)):
                raise ValueError("source descriptor is not independent golden")
            lease_history.append(int(lease))
            jobs.append(bank)
        elif kind == "TAKE":
            _, cycle, epoch, lease, position, data, metadata, last = parts
            if bank is None or bank["published"] or len(bank["take"]) >= 512:
                raise ValueError("duplicate/unowned private take")
            ordinal = len(bank["take"])
            if int(epoch) != bank["epoch"]:
                raise ValueError("take changed epoch")
            if int(data, 16) != golden_word(bank["job"], ordinal):
                raise ValueError("private data differs from independent source")
            legal = (
                int(position) == ordinal
                and int(last) == (ordinal == 511)
                and int(lease) == bank["lease"]
                and int(metadata, 16) == golden_metadata(bank["job"])
            )
            if bank["first_metadata"] is None:
                bank["first_metadata"] = int(metadata, 16)
            locally_bad = (
                int(position) != ordinal
                or int(last) != (ordinal == 511)
                or int(metadata, 16) != bank["first_metadata"]
                or int(lease) != bank["lease"]
            )
            bank["local_bad"] |= locally_bad
            if locally_bad and bank["first_bad_token"] is None:
                bank["first_bad_token"] = (int(cycle), int(position), int(lease))
            bank["poison"] |= not legal
            bank["take"].append(int(cycle))
        elif kind == "CERT":
            _, cycle, epoch, lease, metadata, good = parts
            if bank is None or bank["certificate_consumed"]:
                raise ValueError("unowned or duplicate consumed certificate")
            bank["certificate_consumed"] = True
            legal = (
                int(epoch) == bank["epoch"]
                and int(lease) == bank["lease"]
                and int(metadata, 16) == golden_metadata(bank["job"])
                and int(good) == 1
            )
            bank["certificate"] = legal
            bank["certificate_cycle"] = int(cycle)
            bank["poison"] |= not legal
        elif kind == "SEAL":
            if bank is None or bank["sealed"] or len(bank["take"]) != 512:
                raise ValueError("seal before complete exactly-once payload")
            if (
                int(parts[1]) != bank["take"][-1] + 2
                or bank["local_bad"]
                or bank["fault"]
            ):
                raise ValueError("wrong drain latency or invalid seal")
            if (int(parts[2]), int(parts[3])) != (bank["epoch"], bank["lease"]):
                raise ValueError("seal ownership mismatch")
            bank["sealed"] = True
            bank["seal_cycle"] = int(parts[1])
            seals += 1
        elif kind == "PUB":
            if (
                bank is None
                or not bank["sealed"]
                or not bank["certificate"]
                or bank["published"]
                or bank["poison"]
                or bank["fault"]
            ):
                raise ValueError("uncertified/duplicate publication")
            if (
                int(parts[1]) < bank["take"][-1] + 3
                or int(parts[1]) <= bank["seal_cycle"]
                or int(parts[1]) <= bank["certificate_cycle"]
            ):
                raise ValueError("publication before drain")
            if (int(parts[2]), int(parts[3])) != (bank["epoch"], bank["lease"]):
                raise ValueError("publication ownership mismatch")
            bank["published"] = True
            published += 1
        elif kind == "OUT":
            _, cycle, epoch, lease, position, data, metadata, last = parts
            if bank is None or not bank["published"] or bank["fault"]:
                raise ValueError("unpublished/faulted output")
            ordinal = bank["read"]
            if (
                (int(epoch), int(lease), int(position), int(last))
                != (bank["epoch"], bank["lease"], ordinal, int(ordinal == 511))
                or int(data, 16) != golden_word(bank["job"], ordinal)
                or int(metadata, 16) != golden_metadata(bank["job"])
            ):
                raise ValueError("output numerical/metadata/ownership mismatch")
            bank["read"] += 1
            bank["last_read_cycle"] = int(cycle)
            words += 1
        elif kind == "REL":
            if (
                bank is None
                or not bank["published"]
                or bank["read"] != 512
                or bank["fault"]
            ):
                raise ValueError("release before complete valid read")
            if (int(parts[2]), int(parts[3])) != (bank["epoch"], bank["lease"]):
                raise ValueError("release ownership mismatch")
            if int(parts[1]) < bank["last_read_cycle"] + 3:
                raise ValueError("release before ACK synchronization")
            completed += 1
            bank = None
        elif kind == "FAULT":
            # The initialized-low reset is sampled on clock1. The logger sees
            # the pre-NBA unknown register before that first synchronous clear;
            # this exact pre-epoch receipt existed in the original v3 traces.
            # It is not an owned fault, and is accepted nowhere after RESET/JOB.
            if line == "FAULT 1 0 xxxx" and counts["RESET"] == 0 and not jobs:
                continue
            if bank is not None and int(parts[2]) != bank["epoch"]:
                raise ValueError("fault ownership mismatch")
            if bank is not None and int(parts[3], 16):
                bank["fault"] = True
            fault_union |= int(parts[3], 16)
        elif kind == "TWO_EDGE_FAULT":
            match = re.fullmatch(
                r"TWO_EDGE_FAULT cycle=(\d+) pos=(\d+) lease=(\d+)", line
            )
            if match is None or bank is None or bank["first_bad_token"] is None:
                raise ValueError("unowned delayed fault receipt")
            clock, position, lease = map(int, match.groups())
            origin, expected_position, expected_lease = bank["first_bad_token"]
            if (clock, position, lease) != (
                origin + 2,
                expected_position,
                expected_lease,
            ):
                raise ValueError("delayed fault lost original token identity")
            if clock < previous_cycle:
                raise ValueError("delayed fault cycle moved backwards")
            previous_cycle = clock
        elif kind not in ("SEALED_BANK_PASS", "ISSUER_TIMEOUT"):
            raise ValueError(f"unknown receipt: {line}")
    expected_completed = {0: 8, 6: 1, 9: 2, 13: 1, 17: 1, 18: 1}.get(case, 0)
    if completed != expected_completed:
        raise ValueError("incomplete expected healthy inventory")
    if case == 0 and lease_history != [0, 1, 2, 3, 0, 1, 2, 3]:
        raise ValueError("missing drained lease-wrap coverage")
    if case in (1, 2, 3, 4, 7, 8, 11, 12, 14, 15, 16) and published:
        raise ValueError("negative profile published")
    if case == 12 and not re.search(r"^ISSUER_TIMEOUT age=8192$", log, re.MULTILINE):
        raise ValueError("missing independent bounded issuer timeout")
    if int(terminals[0][3]) < previous_cycle:
        raise ValueError("terminal precedes event history")
    # A self-checking bench terminal alone is NOT execution evidence for a
    # negative profile: the finite stimulus and exact cause must be present.
    requirements, required_fault = profile_requirements(case, bit, phase)
    for event, count in requirements.items():
        if counts[event] != count:
            raise ValueError(
                f"profile missing/extra {event} events: {counts[event]} != {count}"
            )
    if fault_union != required_fault:
        raise ValueError("profile missing/wrong fault cause receipt")
    if case in (1, 14, 15) and not any(
        job["local_bad"] or job["poison"] for job in jobs
    ):
        raise ValueError("missing private malformed-token witness")
    if case in (2, 16) and not any(job["poison"] for job in jobs):
        raise ValueError("missing malformed certificate witness")
    if case == 13 and any(
        b - a != 1 for a, b in zip(jobs[0]["take"], jobs[0]["take"][1:])
    ):
        raise ValueError("missing contiguous 512-clock take witness")
    if case == 17 and jobs[0]["certificate_cycle"] != jobs[0]["take"][-1] + (
        201 if phase == 3 else phase + 1
    ):
        raise ValueError("wrong certificate/seal join phase")
    return {
        "completed": completed,
        "published": published,
        "words": words,
        "seals": seals,
        "lease_history": lease_history,
    }


def profile_requirements(case, bit, phase):
    """Literal finite stimulus inventories; no candidate-state-derived counts."""
    expected = {
        "RESET": 1,
        "JOB": 1,
        "TAKE": 512,
        "CERT": 1,
        "SEAL": 1,
        "PUB": 0,
        "OUT": 0,
        "REL": 0,
        "TWO_EDGE_FAULT": 0,
    }
    cause = 0
    if case == 0:
        expected.update(JOB=8, TAKE=4096, CERT=8, SEAL=8, PUB=8, OUT=4096, REL=8)
    elif case == 1:
        expected.update(
            TAKE=256 if phase == 1 else 512, CERT=int(phase == 0), SEAL=int(phase == 0)
        )
        cause = 4 if phase == 0 else 8
    elif case == 2:
        cause = 4
    elif case == 3:
        expected.update(SEAL=int(phase == 3))
        cause = 0x100 << bit
    elif case == 4:
        cause = 0xFF00
    elif case == 5:
        expected.update(PUB=1, OUT=512)
        cause = 16
    elif case == 6:
        expected.update(
            RESET=2,
            JOB=2,
            TAKE=529 if phase == 0 else 1024,
            CERT=1 + int(phase >= 3),
            SEAL=1 + int(phase >= 1),
            PUB=1 + int(phase >= 3),
            OUT=512 + (17 if phase == 4 else 0),
            REL=1,
        )
    elif case in (7, 8, 11):
        cause = {7: 32, 8: 64, 11: 128}[case]
        if case == 11:
            cause |= 32 if bit == 4 else (64 if bit == 5 else 0)
    elif case == 9:
        expected.update(JOB=2, TAKE=1024, CERT=2, SEAL=2, PUB=2, OUT=1024, REL=2)
    elif case == 10:
        expected.update(PUB=1, OUT=17 if phase == 0 else 511)
        cause = 0x8000
    elif case == 12:
        expected.update(CERT=0)
        cause = 0x8000
    elif case in (13, 17):
        expected.update(PUB=1, OUT=512, REL=1)
    elif case == 14:
        expected.update(TAKE=2, CERT=0, SEAL=0, TWO_EDGE_FAULT=1)
        cause = 8
    elif case == 15:
        expected.update(TAKE=512 if bit == 3 else 256, CERT=0, SEAL=0, TWO_EDGE_FAULT=1)
        cause = 2 if bit == 1 else 1
    elif case == 16:
        expected.update(SEAL=0)
        cause = 4
    elif case == 18:
        expected.update(
            RESET=2,
            JOB=2,
            TAKE=529 if phase == 0 else 1024,
            CERT=1 + int(phase != 1),
            SEAL=1 + int(phase >= 2),
            PUB=1 + int(phase >= 3),
            OUT=1024 if phase >= 3 else 512,
            REL=1,
        )
    elif case == 19:
        expected.update(PUB=1, OUT=512)
        cause = 0x400
    else:
        raise ValueError("unknown profile")
    return expected, cause


def logical_state(rtl):
    """Count declared logical registers, not a mapped resource estimate."""
    staged = rtl.split("end else begin : staged", 1)[1]
    staged = re.sub(r"//[^\n]*", "", staged)
    registers = {}
    memory = {}
    for match in re.finditer(r"\breg\s*(?:\[(\d+):0\])?\s+([^;]+);", staged):
        width = int(match[1]) + 1 if match[1] else 1
        for name in match[2].split(","):
            name = name.strip()
            array = re.fullmatch(r"(\w+)\s*\[0:(\d+)\]", name)
            if array:
                memory[array[1]] = width * (int(array[2]) + 1)
            elif re.fullmatch(r"\w+", name):
                if name in registers:
                    raise ValueError("duplicate declared state")
                registers[name] = width
            else:
                raise ValueError(f"unknown state declaration: {name}")
    reused = {
        "metadata_in_hold",
        "metadata_out_hold",
        "write_position",
        "request_toggle",
        "acknowledge_toggle",
        "request_sync",
        "acknowledge_sync",
        "reading",
        "read_all_loaded",
        "read_valid",
        "read_address",
        "read_output_position",
        "read_payload",
    }
    return {
        "registers": registers,
        "memory": memory,
        "all_register_bits": sum(registers.values()),
        "reused_bank_bits": sum(registers[name] for name in reused),
        "new_control_bits": sum(
            value for name, value in registers.items() if name not in reused
        ),
    }
