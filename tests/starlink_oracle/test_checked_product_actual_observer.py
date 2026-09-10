"""Execute the new observer on frozen real-controller actors, never vendor FFT.

The old actor stimulus/assertions and independent numerical actor oracle are
literal. The added full old guard is driven solely from actual candidate ports.
"""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.test_checked_product_actual_binding_probe import (
    ANCHOR,
    BENCH_SHA,
    INCLUDE,
)
from tests.starlink_oracle.test_checked_product_read import clean_env
from tests.starlink_oracle.test_checked_product_top import ACQ, TOP, build
from tests.starlink_oracle.test_prepare_checked_product_actual import API, ORIGIN

OBSERVER = ACQ / "tb" / API["ENABLED_OBSERVER"]
GOLDEN = "starlink_pss_realtime_result_guard_ce6a885e_golden.v"
SHADOW = "starlink_pss_forward_retirement_shadow.sv"
END = '  `include "checked_product_default_observer.svh"\nendmodule\n'


def fixture_source():
    original = (ACQ / "tb" / (TOP + ".sv")).read_text()
    assert hashlib.sha256(original.encode()).hexdigest() == BENCH_SHA
    origin = API["origin_files"](ORIGIN)
    bench = origin["frozen_sources/" + API["TOP"]].decode()
    start = bench.index("  // BEGIN FORWARD_RETIREMENT_SHADOW")
    end = bench.index("  // This second frozen arithmetic chain", start)
    port_shadow = bench[start:end]
    context = """
  localparam REGISTERED_SCHEDULING=1;
  wire [31:0] fast_cycle=fast_cycles;
  integer epoch=0,active_fixture=0;
  integer corrupt_observer=-1;
  reg [4:0] forward_exponents[0:0];
  initial forward_exponents[0]=0; // Declared identity-control actor, not FFT vectors.
  // This monitor calls the ACTUAL observer's unchanged retained-owner task
  // before the existing kind64 force; the continuous watcher owns the interval.
  initial if($test$plusargs("WATCH_RETAINED"))begin
    wait(dut.state==dut.VERIFY_LEASE && dut.held_phase);
    #0.001;checked_begin_retained_watch();
  end
  // Corrupt ONLY the independent observer's private evidence. The DUT and
  // original actor stimulus remain literal; each detector must reject it.
  initial if($value$plusargs("CORRUPT_OBSERVER=%d",corrupt_observer))begin
    case(corrupt_observer)
      0:begin wait(dut.product_handoff_capacity);@(negedge fft_clk);
        checked_origin_lease=checked_origin_lease^2'b01;end
      1:begin wait(dut.input_job_start_private && dut.held_phase);@(negedge fft_clk);
        checked_bound_receipt=0;end
      2:begin wait(dut.checked_product_bank.core_take && dut.product_bank_position==37);
        @(negedge fft_clk);checked_raw_word[37]=checked_raw_word[37]^36'b1;end
      3:begin wait(dut.checked_product_bank.lease_release);@(negedge fft_clk);
        checked_core_index=511;end
      4:begin wait(checked_retained_watch && dut.fast_fault);@(negedge fft_clk);
        checked_retained_lease=checked_retained_lease^2'b01;end
      5:begin wait(dut.state==dut.ACK_DRAIN && !dut.result_busy && dut.forward_handoff_ack);
        #0.001;checked_bound_receipt=0;end
      default:$fatal(1,"OBSERVER_BAD_CORRUPTION_PROFILE");
    endcase
  end
  initial if(kind==66)begin
    wait(dut.checked_product_bank.adapter.reader.raw_valid &&
         dut.checked_product_bank.adapter.reader.raw_position==37);
    @(negedge fft_clk);
    if(target==0)force dut.core_input_ready=0;
    else force dut.core_input_ready=1;
    if(bit_index==0)force dut.checked_product_bank.adapter.reader.raw_metadata=75'h123;
    if(bit_index==1)force dut.checked_product_bank.adapter.reader.raw_position=9'd7;
    if(bit_index==2)force dut.checked_product_bank.adapter.reader.raw_last=1;
    repeat(4)@(negedge fft_clk);
    if(dut.checked_product_bank.reader_reasons[3:0] !==
       (bit_index==0 ? 4'h4 : bit_index==1 ? 4'h1 : 4'h2) ||
       dut.checked_product_bank.core_take || dut.return_commit_valid ||
       checked_core_index>37 || checked_raw_bad_offers<=0)
      $fatal(1,"OBSERVER_RAW_OFFER_BOUNDARY_ESCAPED");
    $display("CHECKED_OBSERVER_RAW_OFFER_PASS kind=%0d ready=%0d reason=%h core=%0d bad_offers=%0d actor_only=1",
      bit_index,target,dut.checked_product_bank.reader_reasons[3:0],checked_core_index,checked_raw_bad_offers);
    $finish;
  end
  final $display("CHECKED_OBSERVER_ACTOR_END kind=%0d jobs=%0d acks=%0d starts=%0d raw_bad=%0d releases=%0d capacity=%0d retained=%0d guard=%0d pre=%0d post=%0d actor_only=1",
    kind,checked_jobs,checked_acks,checked_starts,checked_raw_bad_offers,
    checked_releases,checked_capacity_receipts,checked_retained_checks,forward_checks,
    checked_pre,checked_post);
"""
    extras = context + port_shadow + OBSERVER.read_text()
    ending = END.replace("endmodule\n", extras + "endmodule\n")
    ending += origin["frozen_sources/" + SHADOW].decode() + origin["frozen_sources/" + GOLDEN].decode()
    body = original.replace(ANCHOR, INCLUDE.read_text() + ANCHOR, 1).replace(END, ending, 1)
    # Entire old actor, every old fatal and input pattern, is unchanged.
    restored = body.replace(ending, END, 1).replace(INCLUDE.read_text() + ANCHOR, ANCHOR, 1)
    assert restored == original
    return original, body


@pytest.fixture(scope="module")
def observed(tmp_path_factory):
    original, body = fixture_source()
    path = build(tmp_path_factory.mktemp("actual_observer") / "top", mutation=(TOP + ".sv", original, body))
    for source in (OBSERVER, INCLUDE, Path(__file__), ACQ / "prepare_checked_product_actual.py"):
        shutil.copyfile(source, path / source.name)
    (path / "observer-source-pins.json").write_text(json.dumps({
        "original_actor": BENCH_SHA,
        "original_actual_inventory": API["ORIGIN_INVENTORY"],
        "observer": hashlib.sha256(OBSERVER.read_bytes()).hexdigest(),
        "scope": "actual_observer_on_frozen_controller_actor_not_FFT"}, indent=2))
    return path


def execute(path, kind=0, bit=0, target=0, watch=False, corrupt=-1):
    command = ["vvp", "sim.vvp", f"+CASE={kind}", f"+BIT={bit}", f"+TARGET={target}"]
    if watch:
        command.append("+WATCH_RETAINED")
    if corrupt >= 0:
        command.append(f"+CORRUPT_OBSERVER={corrupt}")
    result = subprocess.run(command, cwd=path, env=clean_env(), text=True,
        capture_output=True, timeout=30, check=False)
    log = result.stdout + result.stderr
    key = f"observer-case-{kind}-bit-{bit}-target-{target}-watch-{int(watch)}-corrupt-{corrupt}"
    (path / (key + ".log")).write_text(log)
    (path / (key + ".json")).write_text(json.dumps({"command": command, "exit": result.returncode}))
    return result.returncode, log


def receipt(log, kind):
    assert not re.search(r"(?im)^(ERROR|FATAL|FAIL)(:|\b)", log), log
    rows = re.findall(r"^CHECKED_OBSERVER_ACTOR_END kind=(\d+) jobs=(\d+) acks=(\d+) starts=(\d+) raw_bad=(\d+) releases=(\d+) capacity=(\d+) retained=(\d+) guard=(\d+) pre=(\d+) post=(\d+) actor_only=1$", log, re.MULTILINE)
    assert len(rows) == 1, log
    values = tuple(map(int, rows[0]))
    assert values[0] == kind and values[8] > 0 and values[9] > 0 and values[10] == values[9], values
    return values


def test_actual_observer_four_healthy_actor_pairs(observed):
    code, log = execute(observed)
    assert code == 0, log
    values = receipt(log, 0)
    assert values[1:6] == (4, 4, 4, 0, 4)
    assert values[6] >= 4
    assert log.count("CHECKED_PRODUCT_TOP_CONTROL_PASS enabled=1 compared=2048 starts=8") == 1


@pytest.mark.parametrize("kind,bit,target", [
    (1, 0, 37), (1, 0, 511), (2, 69, 0), (3, 1, 4),
    (5, 0, 0), (5, 3, 5), (6, 74, 37), (6, 0, 511),
    (7, 69, 511), (8, 1, 37), (9, 0, 2), (9, 1, 2),
])
def test_actual_observer_current_raw_reset_actor_cases(observed, kind, bit, target):
    code, log = execute(observed, kind, bit, target)
    assert code == 0, log
    receipt(log, kind)


def test_actual_observer_continuous_retained_interval(observed):
    code, log = execute(observed, 64, watch=True)
    assert code == 0, log
    values = receipt(log, 64)
    assert values[2] == 1 and values[3] == 0 and values[5] == 0 and values[7] >= 16
    assert log.count("ACTUAL_BINDING_RETAINED_OWNER_PASS live_valid=0 published=1 reader=1 consumed=0 released=0 actor_only=1") == 1


@pytest.mark.parametrize("kind,reason", [(0, "4"), (1, "1"), (2, "2")])
@pytest.mark.parametrize("ready", [0, 1])
def test_exact_active_inverse_before_good_boundary(observed, kind, reason, ready):
    code, log = execute(observed, 66, kind, ready)
    assert code == 0, log
    receipt(log, 66)
    rows = re.findall(rf"^CHECKED_OBSERVER_RAW_OFFER_PASS kind={kind} ready={ready} reason={reason} core=(\d+) bad_offers=(\d+) actor_only=1$", log, re.MULTILINE)
    assert len(rows) == 1 and int(rows[0][0]) <= 37 and int(rows[0][1]) > 0, log


@pytest.mark.parametrize("corrupt,marker", [
    (0, "CHECKED_ACTUAL_UNBOUND_REAL_ACK"),
    (1, "CHECKED_ACTUAL_UNBOUND_INVERSE_START"),
    (2, "CHECKED_ACTUAL_BAD_OR_UNCHECKED_CORE_TOKEN"),
    (3, "CHECKED_ACTUAL_PREMATURE_RELEASE"),
    (4, "CHECKED_ACTUAL_RETAINED_LEASE_CONSUMED_OR_RELEASED"),
    (5, "CHECKED_ACTUAL_CAPACITY_RECEIPT_OWNERSHIP_CHANGED"),
])
def test_independent_observation_evidence_cannot_self_certify(observed, corrupt, marker):
    code, log = execute(observed, 64 if corrupt == 4 else 0, watch=corrupt == 4, corrupt=corrupt)
    assert code != 0 and marker in log and "FATAL" in log, log
