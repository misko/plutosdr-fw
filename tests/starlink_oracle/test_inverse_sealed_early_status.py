"""First-word control and actual third-word status order; no FFT simulation."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location(
    "inverse_receipts", HERE / "test_inverse_sealed_receipts.py"
)
RECEIPTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECEIPTS)
BENCHES, MODEL = RECEIPTS.BENCHES, RECEIPTS.MODEL
PHASES = [0, 1, 714, 1428, 2500, 4285, 5000, 5713, 7500, 9999]


@pytest.fixture(scope="module")
def early_logs(tmp_path_factory):
    root = tmp_path_factory.mktemp("early_status")
    inventory = RECEIPTS.freeze_python_scope(root / "python_scope")
    result = {}
    try:
        for phase in PHASES:
            path = root / f"phase{phase}"
            result[phase] = BENCHES.run_guard(path, 13, phase)
            assessment = MODEL.verify_guard_events(result[phase], 13, phase)
            (path / "event_assessment.json").write_text(
                json.dumps(assessment, sort_keys=True, indent=2)
            )
        path = root / "actual_third_word_phase0"
        result["third"] = BENCHES.run_guard(path, 14)
        assessment = MODEL.verify_guard_events(result["third"], 14)
        (path / "event_assessment.json").write_text(
            json.dumps(assessment, sort_keys=True, indent=2)
        )
    finally:
        RECEIPTS.verify_python_scope(root / "python_scope", inventory)
    return result


@pytest.mark.parametrize("phase", PHASES)
def test_early_status_complete_nonzero_lifecycle_across_clock_phases(early_logs, phase):
    assert MODEL.verify_guard_events(early_logs[phase], 13, phase) == {
        "jobs": 2,
        "takes": 1024,
        "candidate_outputs": 1024,
        "healthy_releases": 2,
    }


def test_actual_third_word_status_join_has_exact_position_bound(early_logs):
    assert MODEL.verify_guard_events(early_logs["third"], 14) == {
        "jobs": 2,
        "takes": 1024,
        "candidate_outputs": 1024,
        "healthy_releases": 2,
    }


@pytest.mark.parametrize("case, key, offered", [(13, 0, 2), (14, "third", 0)])
def test_first_and_third_status_receipts_are_not_interchangeable(
    early_logs, case, key, offered
):
    expected = 0 if case == 13 else 2
    text = early_logs[key]
    assert text.count(f"raw_position={expected}") == 2
    text = text.replace(f"raw_position={expected}", f"raw_position={offered}")
    with pytest.raises(ValueError, match="declared raw output position"):
        MODEL.verify_guard_events(text, case)


@pytest.mark.parametrize(
    "mutation", ["status_missing", "service_missing", "wrong_latency"]
)
def test_early_status_case_cannot_borrow_delayed_status_receipt(early_logs, mutation):
    text = early_logs[0]
    if mutation == "status_missing":
        text = (
            "\n".join(
                line
                for line in text.splitlines()
                if not line.startswith("EARLY_STATUS")
            )
            + "\n"
        )
    elif mutation == "service_missing":
        text = (
            "\n".join(
                line
                for line in text.splitlines()
                if not line.startswith("EARLY_SERVICE")
            )
            + "\n"
        )
    else:
        assert "publication_delta=3" in text
        text = text.replace("publication_delta=3", "publication_delta=2")
    with pytest.raises(ValueError):
        MODEL.verify_guard_events(text, 13)


def test_early_status_bench_strict_inverse_to_final235_stimulus():
    path = BENCHES.ACQ / "tb/tb_starlink_inverse_sealed_guard.sv"
    text = path.read_text()
    addition = """      if((CASE==13 || CASE==14) && status_valid) begin
        if(!core_valid || core_user[8:0]!==(CASE==13?9'd0:9'd2) || status_data!==9)
          $fatal(1,"EARLY_STATUS_RAW_POSITION_PREMISE");
        $display("EARLY_STATUS %0d %0d %0d data=9 raw_position=%0d",fast_cycle,epoch,job,core_user[8:0]);
      end
"""
    line = '    if(CASE==13 || CASE==14) $display("EARLY_SERVICE job=%0d admit=%0d publication=%0d reader_ack=%0d release=%0d original_reuse=%0d candidate_reuse=%0d",job,admission_cycle,candidate_publish,ack_cycle,release_cycle,original_reuse,candidate_reuse);\n'
    for new, old in [
        (addition, ""),
        ("      if(CASE==13 || CASE==14) begin status_valid=(pos==(CASE==13?0:2)); status_data=9; end\n", ""),
        (line, ""),
        ("if(CASE==0 || CASE==1 || CASE==13 || CASE==14)", "if(CASE==0 || CASE==1)"),
        (
            "        if(CASE!=13 && CASE!=14) send_status();\n        drain_job();",
            "        send_status(); drain_job();",
        ),
    ]:
        assert text.count(new) == 1
        text = text.replace(new, old, 1)
    assert (
        hashlib.sha256(text.encode()).hexdigest()
        == "ce1b2a785f956691aa786d0de2f1e0ee11fb1fe3a0a527125a7040d5a1f0ad70"
    )
