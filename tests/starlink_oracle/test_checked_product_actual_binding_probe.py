"""Bounded pre-vendor binding observations; never executes FFT/vendor tools."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_checked_product_read import clean_env
from tests.starlink_oracle.test_checked_product_top import ACQ, TOP, build

INCLUDE = ACQ / "tb/starlink_pss_checked_product_actual_binding_probe.svh"
BENCH_SHA = "3cec22b52104a2d861970347a20bf76d037b05abd5aee3d0e258ff14692c9508"
ANCHOR = "      if(kind==2 || kind==3 || kind==4 || kind==11 || kind==13 || kind==14)begin\n"


def expansion():
    return INCLUDE.read_text()


def restore(candidate):
    marked = expansion() + ANCHOR
    if candidate.count(marked) != 1:
        raise ValueError("full binding probe inverse changed")
    restored = candidate.replace(marked, ANCHOR, 1)
    if hashlib.sha256(restored.encode()).hexdigest() != BENCH_SHA:
        raise ValueError("original full actor bench changed")
    return restored


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    original = (ACQ / "tb" / (TOP + ".sv")).read_text()
    assert hashlib.sha256(original.encode()).hexdigest() == BENCH_SHA
    path = build(tmp_path_factory.mktemp("actual_bindings") / "top", mutation=(
        TOP + ".sv", ANCHOR, expansion() + ANCHOR))
    candidate = (path / (TOP + ".sv")).read_text()
    assert restore(candidate) == original
    for source in (Path(__file__), INCLUDE):
        (path / source.name).write_bytes(source.read_bytes())
    sources = json.loads((path / "sources.json").read_text())
    for source in (Path(__file__), INCLUDE):
        sources[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    (path / "sources.json").write_text(json.dumps(sources, indent=2))
    return path


def execute(path, kind, old=False):
    command = ["vvp", "sim.vvp", f"+CASE={kind}"]
    if old:
        command.append("+REQUIRE_OLD_INTERFACE")
    result = subprocess.run(command, cwd=path, env=clean_env(), text=True,
                            capture_output=True, timeout=30, check=False)
    key = f"probe-{kind}-old-{int(old)}"
    log = result.stdout + result.stderr
    (path / (key + ".log")).write_text(log)
    (path / (key + ".json")).write_text(json.dumps({"command": command, "exit": result.returncode}))
    return result.returncode, log


@pytest.mark.parametrize("kind,current", [(60, "00"), (61, "10"), (62, "0a"), (63, "02")])
def test_actual_preparation_binding_observation(compiled, kind, current):
    code, log = execute(compiled, kind)
    assert code == 0 and not re.search(r"(?im)^(ERROR|FATAL|FAIL)(:|\b)", log), log
    expected = f"ACTUAL_BINDING_PROBE_PASS kind={kind} current={current} no_old_actual_scope_claim=1 actor_only=1"
    assert log.splitlines().count(expected) == 1, log
    assert len(re.findall(rf"^ACTUAL_BINDING_PROBE kind={kind} .*current={current} .*actor_only=1$", log, re.MULTILINE)) == 1, log


@pytest.mark.parametrize("kind,marker", [
    (60, "ACTUAL_BINDING_OLD_READY_RESERVATION_CONTRACT_DIFFERS"),
    (62, "ACTUAL_BINDING_OLD_SINGLE_FRAMING_MASK_DIFFERS"),
])
def test_literal_old_interface_claim_is_rejected(compiled, kind, marker):
    code, log = execute(compiled, kind, True)
    assert code != 0 and "FATAL" in log and marker in log, log
    assert "ACTUAL_BINDING_PROBE_PASS" not in log


def test_faulted_live_head_is_not_lease_release(compiled):
    code, log = execute(compiled, 64)
    assert code == 0 and not re.search(r"(?im)^(ERROR|FATAL|FAIL)(:|\b)", log), log
    assert log.splitlines().count("ACTUAL_BINDING_RETAINED_OWNER_PASS live_valid=0 published=1 reader=1 consumed=0 released=0 actor_only=1") == 1
    assert len(re.findall(r"^ACTUAL_BINDING_RETAINED_OWNER live_valid=0 published=1 reader=1 reader_owned=1 lease=([0-3]) original_lease=\1 consumed=0 release=0 start=0 state=8 actor_only=1$", log, re.MULTILINE)) == 1, log


def test_old_live_valid_ownership_observer_rejected(compiled):
    code, log = execute(compiled, 64, True)
    assert code != 0 and "FATAL" in log and "ACTUAL_BINDING_OLD_LIVE_VALID_AS_OWNER_DIFFERS" in log, log
    assert "ACTUAL_BINDING_RETAINED_OWNER_PASS" not in log


def test_cleared_guard_capacity_is_not_scheduler_receipt(compiled):
    code, log = execute(compiled, 65)
    assert code == 0 and not re.search(r"(?im)^(ERROR|FATAL|FAIL)(:|\b)", log), log
    assert log.splitlines().count("ACTUAL_BINDING_ACK_CAPACITY_PASS ready=0 capacity=0 receipt=1 guard_busy=0 actual_ack=0 actor_only=1") == 1, log


def test_old_drain_ready_receipt_identity_rejected(compiled):
    code, log = execute(compiled, 65, True)
    assert code != 0 and "FATAL" in log and "ACTUAL_BINDING_OLD_DRAIN_READY_EQUALS_RECEIPT_DIFFERS" in log, log
    assert "ACTUAL_BINDING_ACK_CAPACITY_PASS" not in log


def test_full_original_bench_inverse(compiled):
    candidate = (compiled / (TOP + ".sv")).read_text()
    assert restore(candidate) == (ACQ / "tb" / (TOP + ".sv")).read_text()


@pytest.mark.parametrize("old,new", [
    ("kind>=60", "kind>=61"),
    ("ACTUAL_BINDING_PROBE_EARLY_PUBLIC_ACTION", "WEAKENED_PUBLIC_CHECK"),
    ("CHECKED_TOP_BAD_RAW_TOKEN_DELIVERED", "WEAKENED_OLD_CHECK"),
])
def test_full_inverse_rejects_probe_or_original_edits(compiled, old, new):
    candidate = (compiled / (TOP + ".sv")).read_text()
    assert candidate.count(old) == 1
    with pytest.raises(ValueError):
        restore(candidate.replace(old, new, 1))
