"""Offline-only control prototype; scripted ports are never actual FFT evidence."""

import pytest
import json

from tests.starlink_oracle.retained_output_prototype import (
    BASELINE, PINS, RTL, composition_bench, composition_sources, guard_equivalence_bench, inverse_view, run_sv, verify_baseline,
)
from tests.starlink_oracle.retained_output_graph import continuous_graph, state_inventory


def test_original_source_and_vector_pins():
    verify_baseline()
    assert len(PINS) == 17


@pytest.mark.parametrize("kind,name", [
    ("guard", "starlink_pss_result_guard_owner_view.v"),
    ("mailbox", "starlink_pss_mailbox_owner_view.v"),
])
def test_exact_owner_view_inverse(kind, name):
    inverse_view((RTL / name).read_text(), kind)


@pytest.mark.parametrize("kind,name,old,new", [
    ("guard", "starlink_pss_result_guard_owner_view.v", "age <= age + 1'b1", "age <= age"),
    ("guard", "starlink_pss_result_guard_owner_view.v", "assign owner_active = active;", "assign owner_active = 1'b0;"),
    ("mailbox", "starlink_pss_mailbox_owner_view.v", "acknowledge_toggle <= request_sync[1]", "acknowledge_toggle <= 0"),
])
def test_inverse_rejects_body_and_observation_mutants(kind, name, old, new):
    text = (RTL / name).read_text()
    assert old in text
    with pytest.raises(ValueError):
        inverse_view(text.replace(old, new), kind)


@pytest.mark.parametrize("kind", range(24))
def test_owner_public_boundary(tmp_path, kind):
    run_sv(tmp_path / "owner", (RTL / "tb/tb_retained_owner.sv").read_text(),
           [RTL / "starlink_pss_retained_output_owner.v"], parameters=[f"-Ptb.KIND={kind}"])


@pytest.mark.parametrize("kind", range(1, 15))
@pytest.mark.parametrize("offset", range(14))
def test_cutover_raw_event_every_edge(tmp_path, kind, offset):
    run_sv(tmp_path / "cutover", (RTL / "tb/tb_cutover.sv").read_text(),
           [RTL / "starlink_pss_core_job_cutover.v"],
           parameters=[f"-Ptb.KIND={kind}", f"-Ptb.OFFSET={offset}"])


def test_cutover_healthy_closure_and_early_matching_status(tmp_path):
    run_sv(tmp_path / "cutover", (RTL / "tb/tb_cutover.sv").read_text(),
           [RTL / "starlink_pss_core_job_cutover.v"])


@pytest.mark.parametrize("stall", range(3))
@pytest.mark.parametrize("phase", [0.1, 1.3, 4.7])
def test_scripted_three_bank_composition(tmp_path, stall, phase):
    run_sv(tmp_path / "composition", composition_bench(),
           composition_sources(), parameters=[f"-Ptb.STALL={stall}", f"-Ptb.SLOW_PHASE={phase}"])


@pytest.mark.parametrize("side", [0, 1])
@pytest.mark.parametrize("phase", [0.1, 1.3, 2.9, 4.7])
def test_fresh_mailbox_epoch_with_paused_slow_clock(tmp_path, side, phase):
    run_sv(tmp_path / "epoch", (RTL / "tb/tb_retained_epoch.sv").read_text(),
           [RTL / "starlink_pss_mailbox_owner_view.v", RTL / "starlink_pss_retained_epoch_barrier.v",
            RTL / "tb/retained_clock_witness.sv"],
           parameters=[f"-Ptb.SIDE={side}", f"-Ptb.PHASE={phase}"])


def test_unconditional_guard_equivalence_and_unchanged_faults(tmp_path):
    run_sv(tmp_path / "guard", guard_equivalence_bench(), [
        BASELINE / "starlink_pss_realtime_result_guard.v", BASELINE / "starlink_pss_block_mailbox.v",
        RTL / "starlink_pss_result_guard_owner_view.v", RTL / "baseline_tests/tb_starlink_pss_realtime_result_guard.sv",
    ])


@pytest.mark.parametrize("profile", [0, 1])
def test_default_wrapper_unconditional_equivalence(tmp_path, profile):
    run_sv(tmp_path / "default", (RTL / "tb/tb_retained_default.sv").read_text(),
           composition_sources(), parameters=[f"-Ptb.PROFILE={profile}"])


@pytest.mark.parametrize("kind", range(1, 9))
@pytest.mark.parametrize("offset", range(14))
def test_composed_cutover_fault_every_sample(tmp_path, kind, offset):
    result = run_sv(tmp_path / "raw", composition_bench(),
           composition_sources(), parameters=["-DRETAINED_FAULT_STIMULUS",
             f"-Ptb.FAULT_KIND={kind}", f"-Ptb.FAULT_OFFSET={offset}"])
    if (kind, offset) == (1, 13):
        assert result.count("OFFLINE_UNOBSERVABLE") == 1
        assert "read=1536" in result and "expected raw fault" not in result
    else:
        assert "OFFLINE_UNOBSERVABLE" not in result and "expected raw fault" in result


@pytest.mark.parametrize("boundary,kind", [(1, 1), (1, 2), (1, 3), (2, 4), (2, 1), (2, 2), (2, 3)])
def test_original_raw_ready_and_late_ack_boundaries(tmp_path, boundary, kind):
    run_sv(tmp_path / "ack", composition_bench(),
           composition_sources(), parameters=["-DRETAINED_FAULT_STIMULUS",
             f"-Ptb.FAULT_KIND={kind}", f"-Ptb.FAULT_BOUNDARY={boundary}"])


@pytest.mark.parametrize("phase", [0.1, 1.3, 4.7])
def test_retained_provisional_prefix_while_new_forward_exists(tmp_path, phase):
    run_sv(tmp_path / "prefix", composition_bench(),
           composition_sources(), parameters=["-DRETAINED_FAULT_STIMULUS",
             "-Ptb.FAULT_KIND=4", "-Ptb.FAULT_BOUNDARY=3", f"-Ptb.SLOW_PHASE={phase}"])


def test_composition_continuous_graph_and_declared_state(tmp_path):
    run_sv(tmp_path / "graph", composition_bench(), composition_sources())
    vvp = (tmp_path / "graph/sim.vvp").read_text()
    graph = continuous_graph(vvp)
    inventory = state_inventory(vvp, "tb.dut.retained.island")
    (tmp_path / "graph/continuous.json").write_text(json.dumps(graph, indent=2) + "\n")
    (tmp_path / "graph/state.json").write_text(json.dumps(inventory, indent=2) + "\n")
    assert graph["ls_nodes"] > 0
    for owner in [0, 1]:
        assert sum(r["bits"] for r in inventory["variables"]
                   if f".owners[{owner}].result_guard." in r["path"]) == 180
    for module, bits in [("retained_owner", 17), ("cutover", 17), ("epoch_barrier", 9)]:
        assert sum(r["bits"] for r in inventory["variables"] if f".{module}." in r["path"]) == bits
    assert len([r for r in inventory["arrays"] if r["path"].endswith(".payload_memory")]) == 3
    run_sv(tmp_path / "baseline", (RTL / "tb/tb_retained_default.sv").read_text(), composition_sources())
    original = state_inventory((tmp_path / "baseline/sim.vvp").read_text(), "tb.original")
    assert original["declared_bits"] == 2257 and inventory["declared_bits"] == 2480
    assert inventory["declared_bits"] - original["declared_bits"] == 223
    (tmp_path / "graph/baseline-state.json").write_text(json.dumps(original, indent=2) + "\n")


@pytest.mark.parametrize("label", ["L_0x1", "LS_0x1", "LS_0x1_0", "LS_0x1_0_0", "L_0x1_2_3"])
def test_graph_parser_cycle_suffix_mutants(label):
    specimen = f'{label} .functor AND 1, v0xa_0;\nv0xa_0 .net "a", 0 0, {label};\n'
    with pytest.raises(ValueError, match="combinational cycle"):
        continuous_graph(specimen, minimum=1)


def test_graph_unresolved_node_is_not_a_cut():
    with pytest.raises(ValueError, match="unresolved"):
        continuous_graph('L_0x1 .functor AND 1, LS_0x99_0_0;', minimum=1)


@pytest.mark.parametrize("field,value", [
    ("ENABLE_RETAINED_OUTPUT", "-1"), ("ENABLE_RETAINED_OUTPUT", "2"),
    ("ENABLE_RETAINED_OUTPUT", "1'bx"), ("ENABLE_RETAINED_OUTPUT", "1'bz"),
] + [(field, value) for field in ["REGISTERED_SCHEDULING", "BOUNDARY_ROUND_SAT", "REGISTER_OPERANDS", "LOCAL_FIRST_ADMISSION"]
     for value in ["0", "2", "1'bx", "1'bz"]])
def test_literal_public_entry_rejects_bad_or_unknown_parameters(tmp_path, field, value):
    values = dict(ENABLE_RETAINED_OUTPUT="1", REGISTERED_SCHEDULING="1", BOUNDARY_ROUND_SAT="1",
                  REGISTER_OPERANDS="1", LOCAL_FIRST_ADMISSION="1")
    values[field] = value
    params = ",".join(f".{name}({v})" for name, v in values.items())
    text = f"module tb; starlink_pss_fft_bank_owned_retained_output_probe #({params}) dut(); initial #1 $finish; endmodule"
    reason = "ENABLE_RETAINED_OUTPUT must be known" if field == "ENABLE_RETAINED_OUTPUT" else "requires exact R1/B1/O1/L1"
    run_sv(tmp_path / "guard", text, composition_sources(), expected_failure=reason)


def test_full_composition_shadows_are_unconditional():
    text = composition_bench()
    assert "baseline_guard_0" in text and "baseline_guard_1" in text
    for owner in [0, 1]:
        assert f"if(baseline_guard_{owner}.return_data !==" in text
        assert f"if(baseline_guard_{owner}.age !==" in text
        assert f"if(baseline_guard_{owner}.fault_reasons !==" in text


@pytest.mark.parametrize("side", [1, 2])
@pytest.mark.parametrize("phase", [0.1, 1.3, 4.7])
def test_complete_overlap_reset_and_fresh_exact_replay(tmp_path, side, phase):
    result = run_sv(tmp_path / "reset", composition_bench(), composition_sources(),
                    parameters=[f"-Ptb.RESET_SIDE={side}", f"-Ptb.SLOW_PHASE={phase}"])
    assert result.count("OFFLINE_RESET") == 1 and "read=512" in result


def test_published_reader_can_outlive_active_watchdog_without_reuse(tmp_path):
    result = run_sv(tmp_path / "long-reader", composition_bench(), composition_sources(),
                    parameters=["-Ptb.STALL=3", "-Ptb.BLOCKS=2"])
    assert "capacity_claim=0" in result and "read=1024" in result


@pytest.mark.parametrize("kind", [0, 1, 2])
def test_exact_original_active_watchdog_anchor(tmp_path, kind):
    run_sv(tmp_path / "watchdog", (RTL / "tb/tb_retained_watchdog.sv").read_text(),
           [RTL / "starlink_pss_result_guard_owner_view.v"], parameters=[f"-Ptb.KIND={kind}"])


@pytest.mark.parametrize("stall", [4, 5])
@pytest.mark.parametrize("phase", [0.1, 1.3, 4.7])
def test_actual_reader_ack_reachable_forward_phases(tmp_path, stall, phase):
    result = run_sv(tmp_path / "ack-phase", composition_bench(), composition_sources(),
                    parameters=[f"-Ptb.STALL={stall}", f"-Ptb.SLOW_PHASE={phase}"])
    assert "OFFLINE_ACK_PHASE input=0" in result and "read=1536" in result


def test_old_real_ack_with_current_forward_fault_never_grants_reuse(tmp_path):
    result = run_sv(tmp_path / "ack-fault", composition_bench(), composition_sources(),
                    parameters=["-DRETAINED_FAULT_STIMULUS", "-Ptb.FAULT_KIND=1", "-Ptb.FAULT_BOUNDARY=4"])
    assert "reads=512 retained=1" in result


def test_stopped_reader_fails_original_bounded_drain_not_an_invented_active_timeout(tmp_path):
    result = run_sv(tmp_path / "stopped", composition_bench(), composition_sources(),
                    parameters=["-Ptb.STALL=6", "-Ptb.BLOCKS=2"],
                    expected_failure="25000-fast bounded result drain")
    assert "elapsed=25000 retained=1 guard_active=0/0 read=0" in result
