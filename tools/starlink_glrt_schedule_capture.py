"""Bounded Ethernet GLS1 transport test, with retained heads before POP.

Firmware, RX calibration and the exclusive PPU radio lease are external gates.
This test does not acquire a pilot or certify timing/CFO accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

if __package__:
    from .starlink_glrt_capture import radio_state
    from .starlink_glrt_iio import Context, Library
    from .starlink_glrt_schedule_abi import RATE, SAMPLES, ScheduleBatch, ScheduleSnapshot, ScheduledResult
else:
    from starlink_glrt_capture import radio_state
    from starlink_glrt_iio import Context, Library
    from starlink_glrt_schedule_abi import RATE, SAMPLES, ScheduleBatch, ScheduleSnapshot, ScheduledResult

SERIAL = "winbond-db620818a328172c"
URI = "ip:192.168.1.14"
BASE_ABI = "GLF1-1.0-upper-only"


def save(path, value):
    with path.open("x") as stream:
        json.dump(value,stream,indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def retain_text(path, text):
    with path.open("x") as stream:
        stream.write(text+"\n")
        stream.flush()
        os.fsync(stream.fileno())


def snapshot(device, root, number):
    text = device.read("native_schedule_snapshot")
    retain_text(root/f"snapshot-{number:04d}.txt",text)
    return ScheduleSnapshot.from_sysfs(text)


def retire_head(device, root, *, batch, sequence):
    text = device.read("native_schedule_result")
    # Retain even a malformed/unassociated head before reporting its failure.
    # Never pop an unreadable/corrupt head merely to obtain passing cleanup.
    retain_text(root/f"result-{sequence:04d}.txt",text)
    result = ScheduledResult.from_sysfs(text)
    result.require_association(batch,sequence=sequence)
    if device.read("native_schedule_result") != text:
        raise ValueError("scheduled cached head changed before acknowledgement")
    device.command("native_schedule_pop",result.acknowledgement().strip())
    return result


def run_batch(device, root, *, tag, repeats, phase_seed, phase_step, step_delta_q16,
              lead_samples, deadline, clock=time.monotonic, sleep=time.sleep):
    """One finite batch, then a complete retained drain; at most 64 heads.

    All reads/writes are explicit through the device port. Waiting never
    resubmits a descriptor. An uncertain SUBMIT leaves descriptor and snapshots
    for recovery by the owner, rather than duplicating predicted work.
    """
    root.mkdir(exist_ok=False)
    number = 0
    def snap():
        nonlocal number
        value = snapshot(device,root,number); number += 1
        return value

    if clock() >= deadline:
        raise TimeoutError("scheduled batch deadline already elapsed")
    before = snap()
    before.require_drained()
    device.command("native_schedule_command",4)
    cleared = snap()
    cleared.require_drained()
    if cleared.configured or cleared.faults:
        raise ValueError("scheduled CLEAR did not reset counters/faults")
    device.command("native_schedule_command",16)
    based = snap()
    if based.epoch <= before.epoch or based.faults or not based.status & 16:
        raise ValueError("scheduled source epoch did not rebase cleanly")
    start = based.latest_index+lead_samples
    batch = ScheduleBatch(based.epoch,tag,start,0,80000*65536,phase_step*65536,
                          step_delta_q16,phase_seed,repeats,start+(repeats-1)*80000+SAMPLES-1)
    save(root/"descriptor.json",asdict(batch))
    retain_text(root/"submit.txt",batch.encode().strip())
    device.command("native_schedule_submit",batch.encode().strip())
    while True:
        state = snap()
        if state.epoch != batch.epoch or state.configured != repeats:
            raise ValueError("scheduled submission acknowledgement differs from retained descriptor")
        terminal = sum((state.admitted,state.late,state.no_space,state.unavailable,state.expired,state.cancelled))
        if terminal == repeats and state.committed == state.admitted:
            break
        if clock() >= deadline:
            raise TimeoutError("scheduled batch did not retire before the deadline")
        sleep(.005)
    results = []
    for n in range(state.committed):
        if clock() >= deadline:
            raise TimeoutError("scheduled result drain reached its deadline")
        results.append(retire_head(device,root,batch=batch,sequence=n))
    final = snap()
    final.require_drained()
    if final.faults or final.admitted != repeats or len(results) != repeats:
        raise ValueError("scheduled batch lost or invalidated an opportunity")
    for repeat,result in enumerate(results):
        result.require_complete()
        if result.repeat != repeat:
            raise ValueError("scheduled repeat inventory is not consecutive")
    receipt = dict(epoch=batch.epoch,tag=tag,repeats=repeats,first_start=start,
                   last_start=results[-1].start,high_water=final.high_water,
                   terminal_snapshot=asdict(final),status="transport_pass",precision_qualified=False)
    save(root/"summary.json",receipt)
    return receipt


def collect(args, *, library=None, context_factory=Context):
    if args.uri != URI or args.serial != SERIAL or not args.firmware_version:
        raise ValueError("requires the pinned Ethernet .14 receiver and scheduled firmware identity")
    if not 0 < args.tag < 2**32-1 or not 0 <= args.phase_seed < 2**32 or not 0 <= args.phase_step < 2**32:
        raise ValueError("invalid scheduled tag/carrier fields")
    if not 0 <= args.step_delta_q16 < 2**48 or not 6000 <= args.lead_samples <= 6000000:
        raise ValueError("invalid scheduled step delta or source lead")
    args.output.mkdir(parents=True,exist_ok=False)
    started = time.monotonic(); deadline = started+60
    files = [Path(__file__),Path(__file__).with_name("starlink_glrt_schedule_abi.py"),
             Path(__file__).with_name("starlink_glrt_iio.py"),Path(__file__).with_name("starlink_glrt_capture.py"),
             Path(__file__).with_name("starlink_glrt_native_abi.py")]
    save(args.output/"protocol.json",dict(schema="starlink-gls1-scheduled-bringup/v1",
        request={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
        batches=[32,64],sample_rate_hz=RATE,samples_per_repeat=SAMPLES,
        maximum_collection_seconds=60,precision_qualified=False,
        source_sha256={str(f.resolve()):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}))
    context = device = None
    owned = False
    failures = []; batches = []; before = after = None
    try:
        context = context_factory(library or Library(args.libiio),args.uri,args.serial,
                                  args.firmware_version,timeout_ms=2000)
        save(args.output/"identity.json",dict(context.attributes))
        before = radio_state(context)
        if (before["sample_rate_hz"] != RATE or before["tx_powerdown"] != 1 or
            before["rx_lo_hz"] != args.lo_hz or before["rf_bandwidth_hz"] != args.bandwidth_hz):
            raise ValueError("RF configuration differs from pinned request")
        device = context.device("starlink-glrt-iq")
        if (device.read("capture_abi") != BASE_ABI or device.read("native_schedule_abi") != "GLS1-1.0" or
            device.read("native_capture_enable") != "0"):
            raise ValueError("scheduled profile or idle manual mode is not available")
        state = snapshot(device,args.output,0)
        state.require_drained()
        owned = True
        for n,repeats in enumerate((32,64)):
            if time.monotonic()+5 >= deadline:
                raise TimeoutError("insufficient time for another bounded batch")
            batches.append(run_batch(device,args.output/f"batch-{n}",tag=args.tag+n,repeats=repeats,
                phase_seed=args.phase_seed,phase_step=args.phase_step,step_delta_q16=args.step_delta_q16,
                lead_samples=args.lead_samples,deadline=deadline))
        after = radio_state(context)
        if before != after:
            raise ValueError("radio configuration changed during scheduled capture")
    except (OSError,ValueError,RuntimeError) as error:
        failures.append(f"{type(error).__name__}: {error}")
    finally:
        if device is not None and owned:
            try:
                device.command("native_schedule_command",2)
                # On failure, preserve outstanding heads/reservations. Do not
                # CLEAR or pop observations whose evidence was not retained.
                state = snapshot(device,args.output,1)
                state.require_drained()
                device.command("native_schedule_command",4)
                snapshot(device,args.output,2).require_drained()
                if device.read("capture_abi") != BASE_ABI or device.read("native_capture_enable") != "0":
                    raise ValueError("manual/base ownership did not remain idle")
            except (OSError,ValueError,RuntimeError) as error:
                failures.append(f"scheduled cleanup: {type(error).__name__}: {error}")
        if context is not None:
            try: context.close()
            except (OSError,ValueError,RuntimeError) as error:
                failures.append(f"context cleanup: {type(error).__name__}: {error}")
    result = dict(status="failed" if failures else "transport_pass",failures=failures,batches=batches,
                  radio_before=before,radio_after=after,elapsed_seconds=time.monotonic()-started,
                  precision_qualified=False,native_iq_replay_required=True)
    save(args.output/"summary.json",result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri",required=True); parser.add_argument("--serial",required=True)
    parser.add_argument("--firmware-version",required=True); parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--lo-hz",type=int,required=True); parser.add_argument("--bandwidth-hz",type=int,required=True)
    parser.add_argument("--tag",type=int,default=2000001); parser.add_argument("--phase-seed",type=int,default=17)
    parser.add_argument("--phase-step",type=int,default=7310173); parser.add_argument("--step-delta-q16",type=int,default=65536)
    parser.add_argument("--lead-samples",type=int,default=1200000); parser.add_argument("--libiio")
    result = collect(parser.parse_args())
    print(json.dumps(result,indent=2))
    return int(result["status"] != "transport_pass")


if __name__ == "__main__":
    raise SystemExit(main())
