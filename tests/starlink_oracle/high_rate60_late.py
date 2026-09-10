"""Exact reversible context adapters, not duplicate numerical or runtime code."""

from __future__ import annotations

import json
from pathlib import Path

from .high_rate60_bundle import RUNNER, TB, TOP
from .high_rate60_late_recipe import recipe
from .native60_budget import encoded, require, sha

ROOT = Path(__file__).resolve().parents[2]
LOGIC = TB + "bank_native60_late_logic.svh"
NATIVE = TB + "native60_budget_checks.svh"
PARSER = "tests/starlink_oracle/high_rate60_harness_result.py"
PROFILE = recipe()["profile"]
TERMINAL = (
    f"HIGH_RATE60_PASS profile={PROFILE} admitted=894 map_words=447 capture=0 "
    "raw_tuples=0 qualified_tuples=0 packet_words=0 packet_reads=0 "
    "pilot_words=512 bytes=2048 source=16425 original=16423 prime=2 tail=0 "
    "EXPECTED_LATE_REJECTION_NOT_HEALTHY_NATIVE_NOT_CAUSAL_NO_RF_DMA_IIO_PHYSICAL_OR_PRODUCTION_MAP_CLAIM"
)


def check_recipe(value=None):
    expected = recipe()
    require(encoded(expected if value is None else value) == encoded(expected), "late60 recipe/type changed")
    require(8*24+8+32 == expected["command_derived_control_cycles"] <= expected["command_limit_control_cycles"] and
            256*60 <= 160*100, "late command derivation")
    require([34359740256-(x+1) for x in reversed(expected["command_handshake_closed"])] == [-193,-33],
            "late signed lead derivation")
    require(512+34*24 == 1328 and 8+1328+32 <= 2048, "late audit derivation")
    return expected


def registers():
    """Public31-register ABI audit; no native packet word is read."""
    r = check_recipe()
    values = [(0x38,0),(0x3c,0),(0x80,0)]
    values += [(0x84+4*n,int(n in (2,3))) for n in range(14)]
    values += [(address,0) for address in range(0xbc,0xe4,4)]
    values += [(0x4c,r["native_generation"]),(0x5c,0x1a000000),(0x60,r["native_energy"]),(0x64,0)]
    require(len(values) == 31 and len({x[0] for x in values}) == 31 and 0x54 not in dict(values), "late register ABI")
    return values


def inverse(candidate, receipt):
    require(sha(candidate.encode()) == receipt["after_sha256"], "adapted source hash changed")
    for edit in reversed(receipt["edits"]):
        start, after = edit["offset"], edit["after"]
        require(candidate[start:start+len(after)] == after, "inverse exact context changed")
        candidate = candidate[:start] + edit["before"] + candidate[start+len(after):]
    require(sha(candidate.encode()) == receipt["before_sha256"], "complete original body not restored")
    return candidate


class Adapter:
    def __init__(self, source):
        self.original = self.text = source
        self.edits = []

    def replace(self, before, after, count=1):
        require(before and self.text.count(before) == count, f"strict late context count: {before[:80]}")
        start = 0
        for _ in range(count):
            at = self.text.index(before, start)
            self.edits.append({"offset": at, "before": before, "after": after})
            self.text = self.text[:at] + after + self.text[at+len(before):]
            start = at+len(after)

    def section(self, first, end, replacement):
        require(self.text.count(first) == self.text.count(end) == 1, "late exact section delimiters changed")
        start, stop = self.text.index(first), self.text.index(end)
        require(start < stop, "late section order")
        self.replace(self.text[start:stop], replacement)

    def finish(self):
        receipt = {"before_sha256": sha(self.original.encode()), "after_sha256": sha(self.text.encode()), "edits": self.edits}
        require(inverse(self.text,receipt) == self.original, "strict complete-source inverse")
        return self.text, receipt


def adapt_top(original):
    a = Adapter(original)
    a.replace("tb_starlink_pss_60_bank_native_paired", "tb_starlink_pss_60_bank_native_late")
    a.replace("// Healthy447x2 only. STATIC known center is not a causal coarse-guided command.",
              "// Expected expired native request. Healthy coarse/PIL1 numerics remain exact.")
    a.replace('`include "native60_budget_checks.svh"', '`include "native60_late_context.svh"')
    a.replace("wire native_done=native_released;", "wire native_done=late_observation_done;")
    a.replace("source_at_native_release", "source_at_native_observation", count=6)
    a.replace("retained map ownership changed during independent native result lifetime",
              "retained map ownership changed during independent late audit lifetime")
    a.replace("native public release did not preserve independently retained map after source-off",
              "late audit did not preserve independently retained map after source-off")
    a.replace("map_retained_through_native_release=1 native_result_released=1",
              "map_retained_through_late_observation=1 native_result_created=0")
    a.replace("source_checked!=16425 || continuous_checked!=13312 || native_capture_count!=520 ||\n            native.i_core.i_raw_tracking_core.correlator_busy!==1'b1",
              "source_checked!=16425 || continuous_checked!=13312 || native_capture_count!=0 ||\n            native.i_core.i_raw_tracking_core.correlator_busy!==1'b0")
    a.replace("source-off lacks exact finite source/capture and ongoing native compute",
              "late source-off lacks exact finite source and empty native state")
    a.replace("stop=34359751634 capture=520 busy=1", "stop=34359751634 capture=0 busy=0")
    a.section("    wait(native_drain_cycle>=0);", "    if (!map_released", """    @(negedge clk); native_healthy();
    if(late_observation_done!==1 || late_snapshots!=2 || late_register_reads!=62 ||
       native_raw_count!=0 || native_qualified_count!=0 || native_capture_count!=0 ||
       native_admissions!=0 || native_packet_reads!=0 || native_released!==0 || source_off_compute_cycles!=0)
      fail("late complete-source no-native-work inventory");
""")
    a.replace("!native_capture_fft_overlap || !native_compute_overlap || !native_compute_after_stop ||",
              "native_capture_fft_overlap!=0 || native_compute_overlap!=0 || native_compute_after_stop!=0 ||\n        late_fft_after<1 || late_pilot_after<1 ||")
    a.section('    $display("NATIVE60_BUDGET', "    report_clocks();", """    $display("NATIVE60_LATE_FINAL observation=%0d source_off=%0d quiet_start=%0d quiet_end=%0d maximum_axi=%0d sample_checks=%0d control_checks=%0d capture=0 raw=0 qualified=0 packet_reads=0 irq=0 result=0",
      late_observation_cycle,source_off_cycle,quiet_start,quiet_end,maximum_axi_cycles,late_sample_checks,late_control_checks);
""")
    a.replace("source_at_map_release=%0d\",native_capture_fft_overlap", "source_at_map_release=%0d fft_after_reject=%0d pilot_after_reject=%0d\",native_capture_fft_overlap")
    a.replace("source_at_native_observation,source_at_map_release);", "source_at_native_observation,source_at_map_release,late_fft_after,late_pilot_after);")
    a.section('    $display("HIGH_RATE60_PASS ', "    $finish;", '    $display("'+TERMINAL+'");\n')
    return a.finish()


def adapt_native(original):
    a = Adapter(original)
    a.section("  task automatic native_healthy;", "  task automatic configure_native;", '  `include "bank_native60_late_logic.svh"\n')
    a.section("  task automatic read_native_packet(", "`undef N60_CORE", "")
    return a.finish()


def adapt_parser(original):
    a = Adapter(original)
    a.section("def verify_native_component(", "TERMINAL = (", "from .high_rate60_late_result import verify_native_component\n\n\n")
    a.section("TERMINAL = (", "EXPECTED_MARKERS =", "from .high_rate60_late import TERMINAL, PROFILE\n\n")
    # Preserve healthy recipe bounds and all coarse/PIL1 checks; only native
    # context/receipt associations below differ. No synthetic healthy receipts.
    a.replace('adm = native["admission"]', 'adm = native["rejection"]')
    a.replace('(adm["trigger_cycle"], rise_at(34359738560)-8333333),\n                           (b["capture_end"], rise_at(34359740775)+1000)',
              '(adm["trigger_cycle"], rise_at(34359740288)-8333333)')
    a.replace('"native command/capture cycle not on continuous original source coordinate"',
              '"late command cycle not on continuous original source coordinate"')
    a.replace('"source_at_native_release", "source_at_map_release"]',
              '"source_at_native_observation", "source_at_map_release", "fft_after_reject", "pilot_after_reject"]')
    a.replace('min(overlap["capture_actual_fft"],overlap["compute_coarse_pilot"],overlap["compute_after_stop"]) > 0',
              'overlap["capture_actual_fft"] == overlap["compute_coarse_pilot"] == overlap["compute_after_stop"] == 0 and\n            1 <= overlap["fft_after_reject"] <= p["forward_input"] and 1 <= overlap["pilot_after_reject"] <= p["pilot_accepted"]')
    a.replace('overlap["source_at_native_release"]', 'overlap["source_at_native_observation"]')
    a.replace('"map_retained_through_native_release", "native_result_released"',
              '"map_retained_through_late_observation", "native_result_created"')
    a.replace('"map_retained_through_native_release": 1, "native_result_released": 1',
              '"map_retained_through_late_observation": 1, "native_result_created": 0')
    a.replace('0 <= stop["native_capture"] <= 520 and stop["native_busy"] in [0,1]',
              'stop["native_capture"] == stop["native_busy"] == 0')
    a.replace('"HIGH_RATE60_SIMULATION_VERIFIED"', '"HIGH_RATE60_LATE_SIMULATION_VERIFIED"')
    a.replace('"scope": r["scope"]', '"scope": "expected expired native command; healthy coarse/PIL1 only; no causal/RF/physical claim"')
    return a.finish()


def adapt_runner(original):
    a = Adapter(original)
    a.replace("Fixed healthy60upper", "Fixed expected-late60upper")
    a.replace("prepare_starlink_high_rate60_harness.py", "prepare_starlink_high_rate60_late.py", count=2)
    a.replace("set own_name hdl/library/starlink_pss_acquisition/simulate_high_rate60_bank_native_paired.tcl", "set own_name case/simulate_high_rate60_bank_native_late.tcl")
    a.replace("[file join $prepared source_snapshot $own_name]", "[file join $prepared $own_name]")
    a.replace("set vectors [file join $inputs vectors]", "set vectors [file join $inputs healthy vectors]\nset case_dir [file join $inputs case]")
    a.replace("high_rate60_bank_native_paired", "high_rate60_bank_native_late")
    a.replace("tb_starlink_pss_60_bank_native_paired", "tb_starlink_pss_60_bank_native_late")
    a.replace("[file join $acq tb ${bench}.sv]", "[file join $case_dir ${bench}.sv]")
    a.replace("include_dirs [list [file join $acq tb]]", "include_dirs [list $case_dir [file join $acq tb]]")
    a.replace("  foreach name {pilot_mixer_q16.mem", "  add_files -fileset sim_1 -norecurse [file join $case_dir native60_late_registers.mem]\n  foreach name {pilot_mixer_q16.mem")
    a.replace("HIGH_RATE60_SIMULATION_VERIFIED ideal_bank175=1 native264=1 pilot512=1 static_known_center_not_RF=1",
              "HIGH_RATE60_LATE_SIMULATION_VERIFIED ideal_bank175=1 native264_configured=1 native_jobs=0 pilot512=1 expected_expiry_not_RF=1")
    return a.finish()


def adapted_sources(root, healthy):
    methods = [(TOP,"tb_starlink_pss_60_bank_native_late.sv",adapt_top),
               (NATIVE,"native60_late_context.svh",adapt_native),
               (PARSER,"high_rate60_late_context.py",adapt_parser),
               (RUNNER,"simulate_high_rate60_bank_native_late.tcl",adapt_runner)]
    outputs, receipts = {}, {}
    for name, target, adapt in methods:
        source = (root/name).read_text()
        require(sha(source.encode()) == healthy["source_sha256"][name], f"healthy original changed: {name}")
        outputs[target], receipts[target] = adapt(source)
        receipts[target]["original_path"] = name
    outputs["native60_late_registers.mem"] = "".join(f"{v:08x}\n" for pair in registers() for v in pair)
    outputs["inverse.json"] = encoded(receipts).decode()
    return outputs


def verify_results(directory, bundle):
    """Execute the frozen strictly-derived outer verifier; no input log rewrite."""
    healthy = json.loads((bundle/"healthy/bundle.json").read_bytes())
    derived = adapted_sources(bundle/"source_snapshot", healthy)
    actual = (bundle/"case/high_rate60_late_context.py").read_text()
    require(actual == derived["high_rate60_late_context.py"], "derived verifier context changed")
    scope = {"__package__": "tests.starlink_oracle"}
    exec(compile(actual,"<frozen late60 context>","exec"),scope)  # noqa: S102 - exact inverse of pinned local source
    return scope["verify_results"](directory,bundle/"healthy/cohort")
