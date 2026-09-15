#!/usr/bin/env python3
"""Run one bounded activity-triggered 30-MS/s ARM/FPGA tracking cycle."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qualify_glrt_cpu_live20 as live
from tools.review_glrt_cpu_continuity import review_continuity

RATE = 30_000_000
SERIAL = "1040005e0b100007100010000bf33a5d4d"
PROFILE = "sparse10-after-scout16"
CONTINUITY30_PROFILE = "continuity30-after-scout16"
RANKED_CONTINUITY30_PROFILE = "continuity30-ranked-after-scout16"
FRESH_CONTINUITY30_PROFILE = "continuity30-fresh-after-scout1"
PRIOR_CONTINUITY30_PROFILE = "continuity30-prior-after-scout1"
WAIT_PRIOR_CONTINUITY30_PROFILE = "continuity30-prior-wait12-after-scout1"
PROFILES = (PROFILE, "sparse30-after-scout16", "sparse100-after-scout16",
            CONTINUITY30_PROFILE, RANKED_CONTINUITY30_PROFILE, FRESH_CONTINUITY30_PROFILE,
            PRIOR_CONTINUITY30_PROFILE, WAIT_PRIOR_CONTINUITY30_PROFILE)
UPPER_EDGE_LOS = (1_190_312_500, 1_440_312_500, 1_690_312_500, 1_940_312_500)
SCOUT_SAMPLES = 1536 * 16384
FOLLOWUP_SAMPLES = 45000 * 16384
SEGMENT_SAMPLES = 7500 * 16384
CONTINUITY_ROUNDS = 3
WAIT_CONTINUITY_ROUNDS = 12
WAIT_CONTINUITY_SEGMENTS = 3
MAX_ARCHIVE_BYTES = 320 * 1024 * 1024
EXPECTED = {
    "probe": "ca620a31ec5ea5ad98afa53b39a9cfe8e005b293ac89057bda2e872cc95c1304",
    "bank": "d9f3452e45180c560a200bb76c9bfe2d7c46b17560fd46495ea74c50f50547f0",
    "references": "78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2",
}
FILES = {"stdout.json", "stderr.txt", "capture.txt", "scan.iq.ci16", "worker.jsonl",
         "worker.iq.ci16", "grids.u32", "native.journal", "native.coarse.ci16",
         "observer.jsonl", "observer.iq.ci16", *(f"native-{n}.journal" for n in range(1, 4))}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_los(values, profile=PROFILE):
    values = tuple(values)
    if not 2 <= len(values) <= 4 or len(set(values)) != len(values) or any(v not in UPPER_EDGE_LOS for v in values):
        raise ValueError("requires two to four distinct reviewed upper-edge LOs")
    if maximum_source_seconds(len(values), profile) >= 30 * 60:
        raise ValueError("cycle exceeds RF bound")
    return values


def maximum_source_seconds(count, profile=PROFILE):
    if type(count) is not int or not 2 <= count <= 4:
        raise ValueError("invalid scout count")
    if profile in (CONTINUITY30_PROFILE, RANKED_CONTINUITY30_PROFILE,
                   FRESH_CONTINUITY30_PROFILE, PRIOR_CONTINUITY30_PROFILE):
        samples = CONTINUITY_ROUNDS * (count * SCOUT_SAMPLES + SEGMENT_SAMPLES)
    elif profile == WAIT_PRIOR_CONTINUITY30_PROFILE:
        samples = (WAIT_CONTINUITY_ROUNDS * count * SCOUT_SAMPLES +
                   WAIT_CONTINUITY_SEGMENTS * SEGMENT_SAMPLES)
    else:
        samples = count * SCOUT_SAMPLES + FOLLOWUP_SAMPLES
    return samples / 2_500_000


def validate_outputs(output, raid_output):
    output = output.resolve(strict=False);raid_output = raid_output.resolve(strict=False)
    if (not output.is_relative_to(Path("/srv/postgres-nvme")) or
            not raid_output.is_relative_to(Path("/srv/bulk/leo")) or
            output == raid_output or output.exists() or raid_output.exists()):
        raise ValueError("outputs must be new SSD and RAID paths")
    return output, raid_output


def decode_parent(raw, rate, count, exit_code, profile=PROFILE):
    lines = raw.decode().splitlines()
    if len(lines) != 1:
        raise ValueError("ambiguous parent status")
    value = json.loads(lines[0])
    if profile in (CONTINUITY30_PROFILE,RANKED_CONTINUITY30_PROFILE,FRESH_CONTINUITY30_PROFILE,
                   PRIOR_CONTINUITY30_PROFILE,WAIT_PRIOR_CONTINUITY30_PROFILE):
        keys = {"scope", "rate", "result", "rf_sample_limit", "scan_rounds",
                "segments_started", "visits_executed", "track_complete", "selection", "selected_index"}
        expected_scope="bounded_arm_scout_segmented_followup"
        if profile in (RANKED_CONTINUITY30_PROFILE,FRESH_CONTINUITY30_PROFILE,
                       PRIOR_CONTINUITY30_PROFILE,WAIT_PRIOR_CONTINUITY30_PROFILE):
            keys.add("activity_selection")
            expected_scope=("bounded_arm_scout_prior_wait_segmented_followup" if profile==WAIT_PRIOR_CONTINUITY30_PROFILE else
                            "bounded_arm_scout_prior_segmented_followup" if profile==PRIOR_CONTINUITY30_PROFILE else
                            "bounded_arm_scout_fresh_segmented_followup" if profile==FRESH_CONTINUITY30_PROFILE
                            else "bounded_arm_scout_ranked_segmented_followup")
        if set(value) != keys or value["scope"] != expected_scope or value["rate"] != rate:
            raise ValueError("parent status identity differs")
        if profile in (RANKED_CONTINUITY30_PROFILE,FRESH_CONTINUITY30_PROFILE,
                       PRIOR_CONTINUITY30_PROFILE,WAIT_PRIOR_CONTINUITY30_PROFILE):
            expected_policy=("strongest_one_attempt_scan_prior_reacquire_wait12" if profile==WAIT_PRIOR_CONTINUITY30_PROFILE else
                             "strongest_one_attempt_scan_prior_reacquire" if profile==PRIOR_CONTINUITY30_PROFILE else
                             "strongest_one_attempt_scan" if profile==FRESH_CONTINUITY30_PROFILE else
                             "strongest_complete_scan")
            if value["activity_selection"]!=expected_policy: raise ValueError("activity selection policy differs")
        integers = ("result", "rf_sample_limit", "scan_rounds", "segments_started",
                    "visits_executed", "track_complete")
        if any(type(value[k]) is not int for k in integers):
            raise ValueError("parent status types differ")
        rounds=value["scan_rounds"];segments=value["segments_started"];visits=value["visits_executed"]
        scouts=visits-segments
        maximum_rounds=WAIT_CONTINUITY_ROUNDS if profile==WAIT_PRIOR_CONTINUITY30_PROFILE else CONTINUITY_ROUNDS
        maximum_segments=WAIT_CONTINUITY_SEGMENTS if profile==WAIT_PRIOR_CONTINUITY30_PROFILE else maximum_rounds
        valid_counts=(1 <= rounds <= maximum_rounds and 0 <= segments <= min(rounds,maximum_segments) and
                      rounds <= scouts <= rounds*count and visits == scouts+segments)
        expected_limit=scouts*SCOUT_SAMPLES+segments*SEGMENT_SAMPLES
        selected=value["selected_index"]
        valid_selection=(segments == 0 and value["selection"] == "none" and selected is None) or (
            segments > 0 and value["selection"] in ("retained_activity", "native_handoff") and
            type(selected) is int and 0 <= selected < count)
        valid_result=value["result"] in (-7,-6,-5,-4,-3,-2,-1,0,1,3)
        if (not valid_counts or value["rf_sample_limit"] != expected_limit or
                value["track_complete"] not in (0,1) or
                value["track_complete"] > segments or
                (value["track_complete"] and value["result"] != 0) or
                not valid_selection or not valid_result or
                exit_code != (0 if value["result"] == 0 else 1)):
            raise ValueError("parent disposition is inconsistent")
        return value
    keys = {"scope", "rate", "result", "rf_sample_limit", "followup_started",
            "track_complete", "selection", "selected_index"}
    if set(value) != keys or value["scope"] != "bounded_arm_scout_sparse_followup" or value["rate"] != rate:
        raise ValueError("parent status identity differs")
    integers = ("result", "rf_sample_limit", "followup_started", "track_complete")
    if any(type(value[k]) is not int for k in integers) or value["followup_started"] not in (0, 1) or value["track_complete"] not in (0, 1):
        raise ValueError("parent status types differ")
    expected_limit = count * SCOUT_SAMPLES + (FOLLOWUP_SAMPLES if value["followup_started"] else 0)
    if value["rf_sample_limit"] != expected_limit:
        raise ValueError("parent RF limit differs")
    if not value["followup_started"]:
        valid = value["result"] == 0 and not value["track_complete"] and value["selection"] == "none" and value["selected_index"] is None
    else:
        valid = (value["result"] in (-7, -6, -5, -4, -3, -2, -1, 0, 1, 3)
                 and value["track_complete"] == (value["result"] == 0)
                 and value["selection"] in ("retained_activity", "native_handoff")
                 and type(value["selected_index"]) is int and 0 <= value["selected_index"] < count)
    if not valid or exit_code != (0 if value["result"] == 0 else 1):
        raise ValueError("parent disposition is inconsistent")
    return value


def extract_evidence(payload, destination, parent, count):
    if not payload or len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("evidence archive size differs")
    if parent["scope"] in ("bounded_arm_scout_segmented_followup",
                           "bounded_arm_scout_ranked_segmented_followup",
                           "bounded_arm_scout_fresh_segmented_followup",
                           "bounded_arm_scout_prior_segmented_followup",
                           "bounded_arm_scout_prior_wait_segmented_followup"):
        expected_visits=set(range(parent["visits_executed"]))
    else:
        selected = parent["selected_index"]
        expected_visits = set(range(count) if selected is None else range(selected + 1))
        if parent["followup_started"]:
            expected_visits.add(count)
    seen_files, seen_visits, seen_dirs = set(), set(), set()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        members = archive.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "evidence" or member.issym() or member.islnk():
                raise ValueError("unsafe evidence member")
            if member.isdir():
                seen_dirs.add(path)
                continue
            if not member.isfile():
                raise ValueError("non-regular evidence member")
            if path.parts == ("evidence", "visits.txt"):
                if path in seen_files:
                    raise ValueError("duplicate visit journal")
                seen_files.add(path)
                continue
            if len(path.parts) != 3 or not path.parts[1].startswith("visit-") or path.parts[2] not in FILES:
                raise ValueError("unexpected evidence member")
            try:
                number = int(path.parts[1][6:])
            except ValueError as error:
                raise ValueError("invalid visit directory") from error
            if number not in expected_visits or path in seen_files:
                raise ValueError("unexpected or duplicate visit evidence")
            seen_visits.add(number);seen_files.add(path)
        if PurePosixPath("evidence/visits.txt") not in seen_files or seen_visits != expected_visits:
            raise ValueError("incomplete visit evidence")
        allowed_dirs = {PurePosixPath("evidence"), *(PurePosixPath(f"evidence/visit-{n}") for n in expected_visits)}
        if not seen_dirs <= allowed_dirs:
            raise ValueError("unexpected evidence directory")
        for number in expected_visits:
            required = {PurePosixPath(f"evidence/visit-{number}/{name}") for name in ("stdout.json", "stderr.txt", "capture.txt", "worker.jsonl")}
            if not required <= seen_files:
                raise ValueError("missing required child evidence")
        destination.mkdir(parents=True, exist_ok=False)
        archive.extractall(destination, filter="data")
    return len(seen_files)


def manifest(root):
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
        rows.append(f"{digest(path.read_bytes())}  {path.relative_to(root)}")
    data = ("\n".join(rows) + "\n").encode()
    (root / "SHA256SUMS").write_bytes(data)
    return data


def dry_run_plan(los, hashes, output, raid_output, profile=PROFILE):
    return {"scope":"bounded_radio_local_activity_sparse_followup_dry_run", "rf_collection":False,
        "serial":SERIAL, "rate":RATE, "profile":profile, "los":list(los),
        "maximum_source_seconds":maximum_source_seconds(len(los),profile), "payload_sha256":hashes,
        "output":str(output), "raid_output":str(raid_output), "next_action":"repeat without --dry-run"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--lo-hz", required=True, nargs="+", type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--raid-output", required=True, type=Path)
    parser.add_argument("--profile", choices=PROFILES, default=PROFILE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args();los = validate_los(args.lo_hz, args.profile)
    args.output, args.raid_output = validate_outputs(args.output, args.raid_output)
    plan, layout = live.g.deployment_identity(args.deployment, serial=SERIAL, host=live.ENDPOINT[1])
    if plan["expected_firmware"] != "glrt-iq-tracking-r30000000-v1":
        raise ValueError("deployment is not the reviewed 30-MS/s image")
    payload = {"probe": args.binary.read_bytes(), "bank": (live.EVIDENCE / "coarse-bank.ci16").read_bytes(),
               "references": (live.EVIDENCE / "direct-references.ci16").read_bytes()}
    hashes = {name: digest(data) for name, data in payload.items()}
    if hashes != EXPECTED:
        raise ValueError("payload identity differs")
    if args.dry_run:
        print(json.dumps(dry_run_plan(los, hashes, args.output, args.raid_output, args.profile), indent=2));return
    args.output.mkdir(parents=True)
    receipt = {"scope": "bounded_radio_local_activity_sparse_followup", "serial": SERIAL, "rate": RATE,
               "los": los, "profile": args.profile, "maximum_source_seconds": maximum_source_seconds(len(los),args.profile),
               "payload_sha256": hashes, "status": "started", "started_ns": time.time_ns()}
    def save(): (args.output / "operator.json").write_text(json.dumps(receipt, indent=2) + "\n")
    save();remote = None;staged = mounted = False;review_error=None
    authority = live.LocalCaptureAuthority(Path("/srv/bulk/leo/control"),
        (live.RadioResource("radio_pluto_5d4d", SERIAL, "ip:" + live.ENDPOINT[1]),))
    try:
        lease = authority.claim(("radio_pluto_5d4d",), task_id="gli20-activity-" + args.output.name,
                                task_kind=live.CaptureTaskKind.QUALIFICATION)
    except Exception as error:
        receipt.update(status="admission_refused", error=f"{type(error).__name__}: {error}", rf_samples_collected=0);save()
        raise
    with lease, live.acquire_radio_lock(SERIAL):
        transport = live.b.BoundSshBootstrapTransport(interface=None, host=live.ENDPOINT[1],
            password=live.PASSWORD.read_text().strip(), known_hosts_file=live.EVIDENCE / "radio20.known_hosts")
        ssh = ["sshpass", "-f", str(live.PASSWORD), "ssh", "-o", "StrictHostKeyChecking=yes",
               "-o", "UserKnownHostsFile=" + str(live.EVIDENCE / "radio20.known_hosts"),
               "-o", "ConnectTimeout=5", "root@" + live.ENDPOINT[1]]
        def run(command, data=None, timeout=45):
            return subprocess.run([*ssh, command], input=data, capture_output=True, timeout=timeout)
        receipt["before"] = live.g.attest_tx_safe_idle(transport, plan, serial=SERIAL, host=live.ENDPOINT[1], layout=layout.return_iio_layout);save()
        try:
            memory = run("cat /proc/meminfo");memory.check_returncode();live.preflight_memory(memory.stdout.decode(), 45000, receipt)
            import iio
            context = iio.Context("ip:" + live.ENDPOINT[1])
            try:
                context.set_timeout(5000)
                receipt["configured"] = live.configure_idle_rx(context, rate=RATE, lo_hz=los[0], evidence=receipt,
                    memory_info=memory.stdout.decode(), blocks=45000)
                receipt["calibration"] = {};live.g.calibrate_rx(context.find_device("ad9361-phy"), source_rate=RATE, evidence=receipt["calibration"])
            finally:
                live._close_iio_context(iio, context)
            remote = "/tmp/gli-activity-" + uuid.uuid4().hex
            run("mkdir " + shlex.quote(remote)).check_returncode();staged = True
            run("mount -t tmpfs -o size=320m,nosuid,nodev tmpfs " + shlex.quote(remote)).check_returncode();mounted = True
            for name, data in payload.items():
                run("cat > " + shlex.quote(remote + "/" + name), data).check_returncode()
            run("chmod 700 " + shlex.quote(remote + "/probe")).check_returncode()
            run("mkdir " + shlex.quote(remote + "/evidence")).check_returncode()
            command = [remote + "/probe", str(RATE), SERIAL, remote + "/bank", remote + "/references",
                       remote + "/evidence", *map(str, los), args.profile]
            result = run(shlex.join(command), timeout=1000 if args.profile==WAIT_PRIOR_CONTINUITY30_PROFILE else 430)
            (args.output / "stdout.json").write_bytes(result.stdout);(args.output / "stderr.txt").write_bytes(result.stderr)
            archive = run("tar -C " + shlex.quote(remote) + " -cf - evidence", timeout=90);archive.check_returncode()
            (args.output / "evidence.tar").write_bytes(archive.stdout)
            parent = decode_parent(result.stdout, RATE, len(los), result.returncode,args.profile);receipt["parent"] = parent
            receipt["retained_files"] = extract_evidence(archive.stdout, args.output / "retained", parent, len(los))
            if args.profile in (CONTINUITY30_PROFILE,RANKED_CONTINUITY30_PROFILE,FRESH_CONTINUITY30_PROFILE,
                                PRIOR_CONTINUITY30_PROFILE,WAIT_PRIOR_CONTINUITY30_PROFILE):
                try:
                    receipt["continuity_review"] = review_continuity(
                        (args.output / "retained/evidence/visits.txt").read_text(), parent,
                        serial=SERIAL, los=los)
                except Exception as error:
                    review_error=f"{type(error).__name__}: {error}"
                    receipt["continuity_review"]={"status":"failed","error":review_error}
            receipt["status"] = ("review_failed" if review_error else
                "track_complete_review_pending" if parent["track_complete"] else "review_pending")
        finally:
            if mounted:
                run("umount " + shlex.quote(remote), timeout=45).check_returncode();mounted = False
            if staged:
                run("rmdir " + shlex.quote(remote), timeout=45).check_returncode()
            receipt["after"] = live.g.attest_tx_safe_idle(transport, plan, serial=SERIAL, host=live.ENDPOINT[1], layout=layout.return_iio_layout)
            receipt["radio_restored"] = receipt.get("before") == receipt["after"];save()
    if not receipt.get("radio_restored"):
        raise ValueError("radio state differs after cycle")
    source_manifest = manifest(args.output);shutil.copytree(args.output, args.raid_output)
    if (args.raid_output / "SHA256SUMS").read_bytes() != source_manifest:
        raise ValueError("RAID manifest differs")
    for row in source_manifest.decode().splitlines():
        expected, name = row.split("  ", 1)
        if digest((args.raid_output / name).read_bytes()) != expected:
            raise ValueError("RAID evidence differs")
    if review_error:
        raise ValueError("continuity review failed after evidence publication: "+review_error)
    print(json.dumps({"status": receipt["status"], "track_complete": receipt["parent"]["track_complete"],
                      "output": str(args.output), "raid_output": str(args.raid_output)}))


if __name__ == "__main__":
    main()
