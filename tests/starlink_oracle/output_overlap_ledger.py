"""Bounded, read-only reconstruction and conditional three-bank scheduling.

The input is the accepted L1 175 MHz trace, not a newly simulated design.
The counterfactual deliberately changes ownership scheduling, never arithmetic.
"""

import argparse
import collections
import csv
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import sys

RECIPE = Path(__file__).with_name("output_overlap_recipe.json")
RECIPE_SHA = "1fb118404547d0a3eb13f72d969a5ee80687aec5a388c285839106d1e7fcc688"
LOG_SHA = "ead881d85bbcc6325e6300b8b26ef62ada0db4defce9ae91962db726c1f85e74"
HEADER = "cycle,epoch,profile,running,state,core_resetn,admit,config,inverse,core_input,core_output,status,guard_commit,forward_committed,product_commit,handoff_ack,result_busy,source_valid,source_ready,product_read_valid,product_read_ready,output_bank_ready,fault,block_start"
RUNTIME_PINS = {
    "starlink_pss_fft_bank_owned_local_admission_probe.v": "0cb54617eb6757e1d6c719d97b0fd5002ec7f6105c8c4b50c41eba67d4306235",
    "starlink_pss_realtime_result_guard.v": "09ab35339d55ddf88e813830322d21574d0794c489c9749f68113e9da7807be2",
    "starlink_pss_block_mailbox.v": "e85122eb6689ff49b31aa5a0c200e2666786629055b4f45856fe79fb829dbb55",
    "tb_starlink_pss_local_admission_actual.sv": "a347cd6ec4bb3e888f0ce171aedb7c4a85cebea4932bc880f348a75ada5ae238",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha_file(path, limit=40_000_000):
    require(path.is_file() and not path.is_symlink(), "regular bounded input required")
    require(path.stat().st_size <= limit, "input size limit")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1_048_576), b""):
            h.update(chunk)
    return h.hexdigest()


def recipe():
    require(sha_file(RECIPE) == RECIPE_SHA, "frozen recipe changed")
    return json.loads(RECIPE.read_text())


@dataclass(frozen=True)
class Clocks:
    mhz: int = 175

    @property
    def half(self):
        require(type(self.mhz) is int and self.mhz > 0, "integer frequency")
        return (1_000_000_000 + self.mhz) // (2 * self.mhz)

    def fast(self, cycle):
        return (2 * cycle + 1) * self.half

    @staticmethod
    def slow(cycle):
        return 6_300_000 + cycle * 10_000_000

    def next_fast(self, time_fs):
        return (time_fs - self.half) // (2 * self.half) + 1

    @staticmethod
    def next_slow(time_fs):
        return (time_fs - 6_300_000) // 10_000_000 + 1


def source_block(clocks, profile, previous_commit_slow, previous_forward):
    """Original eager producer, not an arbitrary continuous native source."""
    r = recipe()
    last_read = previous_forward + r["fft_input_last_delta"]
    # ACK samples at slow S1/S2; producer observes old sync2 at S3.
    ready_slow = clocks.next_slow(clocks.fast(last_read)) + 2
    offered_slow = previous_commit_slow + r["producer_interblock_min_slow_edges"]
    first = max(ready_slow, offered_slow)
    pauses = 40 * r["producer_profile1_pause_edges"] if profile else 0
    commit = first + 511 + pauses
    visible = clocks.next_fast(clocks.slow(commit)) + 4
    # The wire becomes ready after S2; CSV samples it on the next fast edge.
    ready_observed = clocks.next_fast(clocks.slow(ready_slow - 1))
    return {"source_first_slow": first, "source_commit_slow": commit,
            "source_visible_fast": visible, "source_ready_observed_fast": ready_observed}


def output_reads(clocks, profile, publication, ready=None):
    """Original 2-sync + read-start + prefetch, actual final-read ACK only."""
    if ready is None:
        ready = lambda s: profile == 0 or s % 17 < 13
    s = clocks.next_slow(clocks.fast(publication)) + 4
    accepted = []
    for _ in range(25_000):
        if ready(s):
            accepted.append(s)
            if len(accepted) == 512:
                break
        s += 1
    require(len(accepted) == 512, "reader did not drain within unchanged bounded observation")
    return {"first_read_slow": accepted[0], "last_read_slow": accepted[-1],
            "ack_observed_fast": clocks.next_fast(clocks.slow(accepted[-1])) + 2}


def read_actual(trace, log):
    r = recipe()
    require(sha_file(trace) == r["trace_sha256"], "wrong original trace")
    require(sha_file(log, 1_000_000) == LOG_SHA, "wrong original log")
    epochs = {e: {"jobs": [], "source_visible": [], "source_ready": [],
                  "output_ready": []} for e in (1, 2)}
    previous = {}; job = None; count = 0
    with trace.open() as stream:
        reader = csv.DictReader(stream)
        require(",".join(reader.fieldnames) == HEADER, "trace header")
        for raw in reader:
            count += 1
            require(count <= 600_000, "trace row bound")
            if raw["epoch"] not in ("1", "2") or raw["running"] != "1":
                continue
            row = {k: int(v) for k, v in raw.items()}
            e, c = row["epoch"], row["cycle"]
            require(row["fault"] == 0, "healthy trace fault")
            data = epochs[e]; prev = previous.get(e, {})
            for signal, key in (("source_valid", "source_visible"),
                                ("source_ready", "source_ready"),
                                ("output_bank_ready", "output_ready")):
                if row[signal] == 1 and prev.get(signal, 0) == 0:
                    data[key].append(c)
            if row["admit"]:
                job = {"admit": c, "inverse": row["inverse"], "epoch": e,
                       "block_start": row["block_start"], "input": [], "output": [],
                       "status": [], "config": [], "commit": [], "product": [], "handoff": []}
                data["jobs"].append(job)
            if job is not None and job["epoch"] == e:
                for signal, key in (("core_input", "input"), ("core_output", "output"),
                                    ("status", "status"), ("config", "config"),
                                    ("guard_commit", "commit"), ("product_commit", "product"),
                                    ("handoff_ack", "handoff")):
                    if row[signal]:
                        job[key].append(c)
                if row["guard_commit"]:
                    job["source_full_at_commit"] = row["source_valid"]
                    job["product_read_valid_at_commit"] = row["product_read_valid"]
            previous[e] = row
    require(count == 590_066, "original row inventory")
    markers = {}
    pattern = re.compile(r"BANK_(CAPTURE_START|CAPTURE_COMMIT|OUTPUT_START|OUTPUT) epoch=(\d+) profile=(\d+) block=(\d+) time_ns=([\d.]+)")
    for match in pattern.finditer(log.read_text()):
        kind, epoch, profile, block, ns = match.groups()
        if int(epoch) not in epochs:
            continue
        key = (int(epoch), int(block), kind)
        require(key not in markers, "duplicate slow receipt")
        require(int(profile) == r["epochs"][epoch]["profile"], "profile identity")
        fs = int(Decimal(ns) * 1_000_000)
        require((fs - 6_300_000) % 10_000_000 == 0, "slow receipt phase")
        markers[key] = (fs - 6_300_000) // 10_000_000
    for e, data in epochs.items():
        n = r["epochs"][str(e)]["blocks"]
        require(len(data["jobs"]) == 2*n and len(data["source_visible"]) == n,
                "job/source inventory")
        require(sum(key[0] == e for key in markers) == 4*n, "slow receipt inventory")
    return epochs, markers


def reconstruct(epochs, markers):
    """Every original coordinate must match before a what-if is evaluated."""
    r = recipe(); clocks = Clocks(); ledger = []
    for e, data in epochs.items():
        profile = r["epochs"][str(e)]["profile"]
        previous = None
        for b in range(len(data["jobs"]) // 2):
            f, inv = data["jobs"][2*b:2*b+2]
            require((f["inverse"], inv["inverse"]) == (0, 1), "phase order")
            require(f["block_start"] == inv["block_start"] == 0x200000000 + e*65536 + b*447,
                    "source/job identity")
            for job in (f, inv):
                a = job["admit"]
                require(len(job["input"]) == len(job["output"]) == 512, "transform word counts")
                require(job["input"] == [c for c in range(a+5, a+518) if c != a+6],
                        "FFT input service")
                require(job["output"] == list(range(a+1298, a+1810)), "FFT output service")
                require(job["status"] == [a+1300] and job["config"] == [a+3], "status/config service")
                require(job["commit"] == [a+1810], "publication service")
            fp, ip = f["commit"][0], inv["commit"][0]
            require(f["product"] == [fp+5] and f["handoff"][0] == fp+10,
                    "product publication/visibility")
            require(inv["admit"] == fp+17, "forward handoff latency")
            first = markers[e,b,"CAPTURE_START"]; commit = markers[e,b,"CAPTURE_COMMIT"]
            source = {"source_first_slow": first, "source_commit_slow": commit,
                      "source_visible_fast": data["source_visible"][b]}
            require(source["source_visible_fast"] == clocks.next_fast(clocks.slow(commit))+4,
                    "source visibility CDC")
            if previous:
                modeled = source_block(clocks, profile, previous["source_commit_slow"],
                                       previous["forward_admit_fast"])
                require(all(source[k] == modeled[k] for k in source), "source eager-producer replay")
                require(modeled["source_ready_observed_fast"] in data["source_ready"], "source ready replay")
                source = modeled
                require(f["admit"] == max(previous["ack_observed_fast"]+7,
                                         source["source_visible_fast"]+2), "original dispatch replay")
            else:
                source["source_ready_observed_fast"] = None
                require(f["admit"] == source["source_visible_fast"]+2, "initial dispatch")
            read = output_reads(clocks, profile, ip)
            require(read["first_read_slow"] == markers[e,b,"OUTPUT_START"] and
                    read["last_read_slow"] == markers[e,b,"OUTPUT"], "output read replay")
            require(read["ack_observed_fast"] in data["output_ready"], "actual ACK replay")
            row = {"epoch": e, "block": b, "profile": profile, **source,
                   "forward_admit_fast": f["admit"], "forward_publication_fast": fp,
                   "product_publication_fast": fp+5, "product_visible_fast": fp+10,
                   "inverse_admit_fast": inv["admit"], "inverse_publication_fast": ip,
                   "next_source_full_at_inverse_publication": inv["source_full_at_commit"],
                   "product_read_valid_at_inverse_publication": inv["product_read_valid_at_commit"], **read}
            ledger.append(row); previous = row
    return ledger


def conditional(ledger, mhz=175, extra=0):
    """Proposed owner handoff AT publication; original RTL does not do this."""
    r = recipe(); clocks = Clocks(mhz); rows = []; previous = None
    for original in ledger:
        e, b, profile = (original[k] for k in ("epoch", "block", "profile"))
        if b == 0:
            previous = None
            source = {k: original[k] for k in ("source_first_slow", "source_commit_slow")}
            source["source_visible_fast"] = clocks.next_fast(clocks.slow(source["source_commit_slow"]))+4
            fa = source["source_visible_fast"]+2
        else:
            source = source_block(clocks, profile, previous["source_commit_slow"], previous["forward_admit_fast"])
            fa = max(previous["inverse_publication_fast"] + r["retained_output_publication_to_forward_admission"],
                     source["source_visible_fast"]+r["source_discovery_to_admission"])
        fp = fa+r["guard_publication_delta"]
        ia = fp+r["forward_publication_to_inverse_admission"]+extra
        if previous:
            ia = max(ia, previous["ack_observed_fast"] + r["retained_context_clear_after_real_ack"]+2)
        ip = ia+r["guard_publication_delta"]
        read = output_reads(clocks, profile, ip)
        row = {"kind": "CONDITIONAL_NOT_RTL", "epoch": e, "block": b, "profile": profile,
               "mhz": mhz, "extra_pipeline_cycles": extra, **source,
               "forward_admit_fast": fa, "forward_publication_fast": fp,
               "product_publication_fast": fp+5, "inverse_admit_fast": ia,
               "inverse_publication_fast": ip, **read}
        if previous:
            row["pair_period_fast"] = fa-previous["forward_admit_fast"]
            row["pair_period_fs"] = row["pair_period_fast"]*2*clocks.half
            # Count actual input edges that fall inside the previous retained
            # reader ownership interval, not just static state elapsed time.
            row["forward_input_edges_while_old_output_owned"] = sum(
                previous["inverse_publication_fast"] < c < previous["ack_observed_fast"]
                for c in range(fa+5, fa+518) if c != fa+6)
            row["old_read_edges_during_forward_input_span"] = sum(
                clocks.fast(fa+5) <= clocks.slow(s) <= clocks.fast(fa+517)
                and (profile == 0 or s % 17 < 13)
                for s in range(previous["first_read_slow"], previous["last_read_slow"]+1))
            row["old_output_released_before_next_inverse"] = ia >= previous["ack_observed_fast"]+3
        rows.append(row); previous = row
    return rows


@dataclass
class RetainedConsumer:
    """Small abstract specification for counterexamples, NOT candidate RTL."""
    epoch: int = 0
    armed: bool = True
    lease: int | None = None
    descriptor: int | None = None
    faulted: bool = False

    def publish(self, lease, descriptor, producer_closed):
        require(self.armed and not self.faulted and self.lease is None and producer_closed,
                "publication requires closed producer and unowned output")
        self.lease, self.descriptor = lease, descriptor

    def start_forward(self, producer_closed):
        require(self.armed and not self.faulted and producer_closed, "unclosed core producer")

    def start_inverse(self):
        require(self.armed and not self.faulted and self.lease is None, "output still owned")

    def acknowledge(self, epoch, lease, final_read):
        require(self.armed and not self.faulted and epoch == self.epoch and
                lease == self.lease and self.lease is not None and final_read, "false/stale ACK")
        self.lease = self.descriptor = None

    def reset(self, common=False):
        if common:
            self.epoch += 1; self.armed = False
            self.lease = self.descriptor = None; self.faulted = False

    def rearm(self, purge_epoch, references_empty):
        require(purge_epoch == self.epoch and references_empty and self.lease is None, "stale rearm")
        self.armed = True


def summary(rows):
    result = {}
    for e in (1, 2):
        rs = [x for x in rows if x["epoch"] == e]
        periods = [b["forward_admit_fast"]-a["forward_admit_fast"] for a,b in zip(rs, rs[1:])]
        result[str(e)] = {"blocks": len(rs), "pair_periods": dict(collections.Counter(periods)),
                          "publication_to_ack": dict(collections.Counter(x["ack_observed_fast"]-x["inverse_publication_fast"] for x in rs))}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); r = recipe()
    require(not args.output.exists() and not args.output.is_symlink() and
            args.output.parent.is_dir() and not args.output.parent.is_symlink(),
            "new output under real existing parent required")
    frozen = args.trace.parents[5]/"frozen_sources"
    dependencies = [RECIPE, Path(__file__), Path(__file__).parents[1]/"test_starlink_output_overlap_ledger.py"]
    for name, digest in RUNTIME_PINS.items():
        path = frozen/name
        require(sha_file(path) == digest, "reviewed runtime dependency changed: "+name)
        dependencies.append(path)
    dependencies.extend([args.trace, args.log])
    before = {str(p): {"sha256": sha_file(p), "bytes": p.stat().st_size} for p in dependencies}
    epochs, markers = read_actual(args.trace, args.log)
    measured = reconstruct(epochs, markers)
    alternatives = []
    for mhz in r["frequency_what_if_mhz"]:
        for extra in r["additional_pipeline_sensitivity_cycles"]:
            rows = conditional(measured, mhz, extra)
            alternatives.append({"mhz": mhz, "extra_cycles": extra, "summary": summary(rows), "blocks": rows})
    proof = {"schema": r["schema"], "recipe_sha256": RECIPE_SHA,
             "trace_sha256": sha_file(args.trace), "log_sha256": sha_file(args.log),
             "original_reconstruction": "PASS_ALL_38_BLOCKS_76_JOBS",
             "actual_summary": summary(measured), "actual_blocks": measured,
             "theoretical_min_mhz_at_29_8us": {
                 "two_observed_admission_to_publication_services_only": 3620/29.8,
                 "proposed_overlap_including_17_and_8_dispatch": 3645/29.8,
                 "proposed_overlap_plus_24_sensitivity": 3669/29.8,
                 "original_maximum_4549": 4549/29.8},
             "counterfactuals": alternatives,
             "limits": "No RTL implementation, FFT simulation, arithmetic change, physical closure or source-capacity qualification"}
    after = {str(p): {"sha256": sha_file(p), "bytes": p.stat().st_size} for p in dependencies}
    require(before == after, "source/input changed during derivation")
    args.output.mkdir()
    (args.output/"ledger.json").write_text(json.dumps(proof, indent=2, sort_keys=True)+"\n")
    snapshot = args.output/"source_snapshot"; snapshot.mkdir()
    for path in dependencies:
        if path != args.trace:  # Preserve exact external 35.7MB trace by hash, not a redundant copy.
            shutil.copyfile(path, snapshot/path.name)
    integrity = {"before": before, "after": after, "equal": True,
                 "host": platform.node(), "platform": platform.platform(),
                 "python": sys.version, "executable": sys.executable,
                 "command": sys.argv,
                 "bulk_trace": "External pinned original, not copied; required to replay"}
    (args.output/"integrity.json").write_text(json.dumps(integrity, indent=2, sort_keys=True)+"\n")
    print(json.dumps({k: proof[k] for k in ("original_reconstruction", "actual_summary", "limits")}, sort_keys=True))


if __name__ == "__main__":
    main()
