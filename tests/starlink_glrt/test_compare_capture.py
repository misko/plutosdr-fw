"""File/coordinate comparison fixtures; no radio or RF-truth claim."""
from __future__ import annotations

import json
import struct

import pytest

from tools.starlink_glrt_abi import Closure, DELAYS, Snapshot
from tools.starlink_glrt_profile import FPGA_GATES, profile
from tools.starlink_glrt_compare_capture import EVIDENCE, compare_capture
from tools.starlink_glrt_replay import digest
from .test_abi import record


def save(path, value):
    path.write_text(json.dumps(value) + "\n")


def refresh_capture(capture):
    summary = json.loads((capture/"summary.json").read_text())
    names = EVIDENCE + (("prefill_snapshot.txt",) if (capture/"prefill_snapshot.txt").exists() else ())
    names += tuple(name for name in ("extension_abi.txt", "baseline_extension_snapshot.txt", "final_extension_snapshot.txt")
                   if (capture/name).is_file())
    summary["evidence_sha256"] = {name: digest(capture/name) for name in names}
    summary["iq_sha256"] = digest(capture/"iq.ci16")
    summary["events_sha256"] = digest(capture/"events.raw")
    save(capture/"summary.json", summary)


def fixture(tmp_path, rate=60000000):
    capture, host = tmp_path/"capture", tmp_path/"host"
    capture.mkdir(); host.mkdir()
    ratio, samples, visit = rate//2500000, 10000, 29
    first = ((1 << 60)//ratio + (2*DELAYS[rate]+ratio-1)//ratio)*ratio
    center = first-DELAYS[rate]
    config = [13107, 19661, 9831, 1]
    protocol = dict(schema="starlink-glrt-iio-capture/v1", serial="fixture", firmware_version="fixture",
                    visit=visit, source_rate=rate, samples=samples, chunk_samples=1000,
                    lo_hz=1400000000, bandwidth_hz=2000000, edge="upper",
                    acquisition_q16=config[0], threshold_q16=config[1], margin_q16=config[2],
                    decisions_off=False)
    save(capture/"protocol.json", protocol)
    identity = {key: {"hw_serial": "fixture", "fw_version": "fixture"}
                for key in ("iq_context", "event_context")}
    save(capture/"identity.json", identity)
    words = [0]*64
    words[20], words[23] = visit, 1
    words[57:61], words[62:64] = config, [rate, DELAYS[rate]]
    def wire(values, count):
        return f"GLR1 00010000 {rate} 2500000 1 0 {rate} 0 {count} {count} 0 0 0 0 " + " ".join(
            f"{w:08x}" for w in values) + "\n"
    (capture/"baseline_snapshot.txt").write_text(wire(words, 0))
    (capture/"initial_snapshot.txt").write_text(wire(words, 0))
    for offset, value in ((0, first), (2, first+(samples-1)*ratio), (4, samples), (6, samples)):
        words[offset:offset+2] = [value & 0xffffffff, value >> 32]
    words[12], words[14], words[19], words[21] = samples*ratio, samples, 24, 1
    words[38] = words[53] = words[55] = 3
    (capture/"final_snapshot.txt").write_text(wire(words, 3))
    raw_events = []
    for sequence, epoch, bin_index in ((0, center+478*ratio+ratio//3, 511),
                                      (1, center+(samples-200)*ratio, 511),
                                      (2, center+478*ratio, 250)):
        event = record(sequence=sequence, visit=visit)
        event[3:5] = [epoch & 0xffffffff, epoch >> 32]
        event[7] = (1 << 27) + bin_index
        raw_events.append(struct.pack("<16I", *event))
    raw_events.append(struct.pack("<16I", *record(visit=99)))
    (capture/"events.raw").write_bytes(b"".join(raw_events))
    (capture/"iq.ci16").write_bytes(b"\0"*(samples*4))
    save(capture/"blocks.json", [{"bytes": 4000, "refill_seconds": .0004}]*10)
    radio = dict(sample_rate_hz=rate, rx_lo_hz=1400000000, rf_bandwidth_hz=2000000, tx_powerdown=1)
    save(capture/"summary.json", dict(schema=protocol["schema"], status="complete", failures=[],
         iq_prefix_attested=True, event_transport_attested=True, received_bytes=4*samples,
         event_records=3, other_visit_event_records=1, radio_before=radio, radio_after=radio))
    refresh_capture(capture)
    save(host/"protocol.json", dict(schema="starlink-glrt-blind-host/v1", fpga_seed_inputs=[],
         edge="upper", sample_rate_hz=2500000, cfo_comparison_band_hz=[-100000, 100000],
         calibration={"center_hz": 0}))
    window = {"start": 0, "candidates": [{"acquisition": {"rank": 0}, "frame_glrt64": [{
        "glrt64": {"tracking_cfo_hz": -5000000/(512*22)}, "engineering_positive": True,
        "support_output_samples": [500, 1204]}]}]}
    save(host/"blind-windows.jsonl", window)
    save(host/"summary.json", dict(schema="starlink-glrt-blind-host/v1", status="complete",
         samples=samples, iq_sha256=digest(capture/"iq.ci16"),
         protocol_sha256=digest(host/"protocol.json"), windows_sha256=digest(host/"blind-windows.jsonl")))
    return capture, host, ratio, center


@pytest.mark.parametrize("rate", [2500000, 60000000])
def test_capture_comparison_keeps_large_counters_fractional_delay_and_excluded_events(tmp_path, rate):
    capture, host, ratio, center = fixture(tmp_path, rate)
    result = compare_capture(capture, host)
    assert result["agreement_observed"]
    assert result["first_output_center_native_index"] == center
    comparison = result["comparison"]
    assert comparison["unmatched_fpga_positives"] == 0
    assert comparison["fpga_positive_comparisons"][0]["matches"][0]["epoch_error_output_samples"] == pytest.approx(
        (ratio//3)/ratio)
    assert len(result["unobservable_fpga_positive_events"]) == 2
    assert result["other_visit_event_records"] == 1
    assert not result["live_detector_qualified"]


@pytest.mark.parametrize("fault", ["iq", "snapshot", "pending", "seeded-host", "event-loss", "legacy"])
def test_capture_comparison_rejects_changed_or_incomplete_evidence(tmp_path, fault):
    capture, host, _, _ = fixture(tmp_path)
    if fault == "iq":
        with (capture/"iq.ci16").open("ab") as stream: stream.write(b"\0\0\0\0")
    elif fault == "snapshot":
        with (capture/"final_snapshot.txt").open("a") as stream: stream.write(" ")
    elif fault == "pending":
        fields = (capture/"final_snapshot.txt").read_text().split()
        fields[14+61] = "00000002"
        (capture/"final_snapshot.txt").write_text(" ".join(fields))
        refresh_capture(capture)
    elif fault == "seeded-host":
        protocol = json.loads((host/"protocol.json").read_text())
        protocol["fpga_seed_inputs"] = ["events.raw"]
        save(host/"protocol.json", protocol)
        summary = json.loads((host/"summary.json").read_text())
        summary["protocol_sha256"] = digest(host/"protocol.json")
        save(host/"summary.json", summary)
    elif fault == "event-loss":
        (capture/"events.raw").write_bytes((capture/"events.raw").read_bytes()[64:])
        refresh_capture(capture)
    else:
        summary = json.loads((capture/"summary.json").read_text())
        summary.pop("evidence_sha256")
        save(capture/"summary.json", summary)
    reason = {"iq": "evidence missing or changed", "snapshot": "evidence missing or changed",
              "pending": "still pending", "seeded-host": "independently acquired",
              "event-loss": "event inventory differs", "legacy": "evidence missing or changed"}[fault]
    with pytest.raises(ValueError, match=reason):
        compare_capture(capture, host)


@pytest.mark.parametrize("fault", [None, "changed", "active", "endpoints"])
def test_prefill_snapshot_is_bound_stopped_and_matches_received_prefix(tmp_path, fault):
    capture, host, ratio, _ = fixture(tmp_path)
    protocol = json.loads((capture/"protocol.json").read_text())
    protocol.update(prefill=True, chunk_samples=2500)
    save(capture/"protocol.json", protocol)
    save(capture/"blocks.json", [{"bytes": 10000, "refill_seconds": .001}]*4)
    fields = (capture/"final_snapshot.txt").read_text().split()
    if fault == "active":
        fields[14+19] = "00000019"
    elif fault == "endpoints":
        for word in (0, 2):
            value = int(fields[14+word], 16) + (int(fields[15+word], 16) << 32) + ratio
            fields[14+word:16+word] = [f"{value & 0xffffffff:08x}", f"{value >> 32:08x}"]
    (capture/"prefill_snapshot.txt").write_text(" ".join(fields))
    refresh_capture(capture)
    if fault == "changed":
        with (capture/"prefill_snapshot.txt").open("a") as stream:
            stream.write(" ")
    if fault is None:
        result = compare_capture(capture, host)
        assert str(capture/"prefill_snapshot.txt") in result["input_sha256"]
    else:
        reason = {"changed": "evidence missing or changed", "active": "active, queued",
                  "endpoints": "endpoints/counts differ"}[fault]
        with pytest.raises(ValueError, match=reason):
            compare_capture(capture, host)


@pytest.mark.parametrize("fault", [None, "changed", "wrong-generation", "lost-vector", "unsettled"])
def test_comparator_rechecks_finite_closure_evidence_and_preserves_large_endpoints(tmp_path, fault):
    capture, host, _, _ = fixture(tmp_path)
    protocol = json.loads((capture/"protocol.json").read_text())
    protocol.update(closure_extension_required=True, detector_profile=profile(FPGA_GATES))
    save(capture/"protocol.json", protocol)
    fields = (capture/"final_snapshot.txt").read_text().split()
    fields[14+30] = fields[14+34] = "00000003"
    (capture/"final_snapshot.txt").write_text(" ".join(fields))
    final = Snapshot.decode(" ".join(fields))
    words = [0]*16
    words[0] = 7
    words[2:4] = [final.u64(2) & 0xffffffff, final.u64(2) >> 32]
    words[8] = words[10] = 3
    if fault == "lost-vector":
        words[10] = 2
    if fault == "unsettled":
        words[0] = 3
    def extension(values, generation=1):
        return f"GLX1 00010000 {generation} 29 60000000 " + " ".join(f"{w:08x}" for w in values)
    (capture/"extension_abi.txt").write_text("GLX1-1.0\n")
    (capture/"baseline_extension_snapshot.txt").write_text(extension([0]*16))
    wire = extension(words, generation=2 if fault == "wrong-generation" else 1)
    (capture/"final_extension_snapshot.txt").write_text(wire)
    summary = json.loads((capture/"summary.json").read_text())
    summary.update(extension_abi="GLX1-1.0", finite_detector_closure_attested=True,
                   finite_detector_closure=Closure.decode(wire).evidence())
    save(capture/"summary.json", summary)
    refresh_capture(capture)
    if fault == "changed":
        (capture/"final_extension_snapshot.txt").write_text(wire+" ")
    if fault is None:
        result = compare_capture(capture, host)
        assert result["finite_detector_closure_attested"]
        assert result["finite_detector_closure"]["native_endpoint"] == final.u64(2) > 1 << 53
    else:
        reason = {"changed": "evidence missing or changed", "wrong-generation": "identity mismatch",
                  "lost-vector": "vectors were lost", "unsettled": "closure is incomplete"}[fault]
        with pytest.raises(ValueError, match=reason):
            compare_capture(capture, host)
