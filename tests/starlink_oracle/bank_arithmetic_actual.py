"""Frozen actual-FFT preparation; scores are an output-derived oracle, not RTL."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACQ = ROOT / "hdl/library/starlink_pss_acquisition"
BASE = "dec20d6371f2d77b6e09c4bcdda2f3d7f8715776"
HISTORICAL_R1_CSV = "25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122"
IP_SHA = "0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d"
CORE_TIMING = {"config_delta": 3, "input_span": 513, "input_last_to_output_first": 781, "commit_delta": 1810}
OLD_BOUNDS = {"watchdog_fast_cycles": 1500000, "drain_fast_cycles": 25000,
              "fault_observation_fast_cycles": 24, "provisional_prefix_words": [128, 132]}
VECTOR_HASHES = {
    "samples_ci16.mem": "4abe27ba953cf49f84d9979966625a2436ad59359b616321e881b42dd4c84723",
    "forward_q17.mem": "d934a8ecd0888c294fc0abfbdbe7c439bff7097ea169b937638c4b7000479bfd",
    "product_q17.mem": "b316522a68529a73d3d8e4121badea61e24621c93a97365e894f5bd416bcecb7",
    "inverse_q17.mem": "c8c5b4e28ab621d0b1d5c1dc288f6e66495b3319d348442ce5d7b8f6ea8025a1",
    "forward_exponents.mem": "18ac6df6a1ae3f19e5153524b33f336a60eabdd6dbd182d46c43450302e4b52f",
    "inverse_exponents.mem": "899b7a2486fd3759c6e4905110fc4d86ffdb6ec884da2a7f2aca4acdfd363dff",
    "upper_edge_pss_kernel_q17.mem": "694d0d9b8dd55368bcaaedec37a7cda3a837d491d592ede60eec57a9821fc99a",
    "scores_u8.mem": "c22f751a2a82244268dd9ea4989c4ff3b5364c172526e80886c5da3d1959e45d",
}
OLD_BENCH = "tb_starlink_pss_fft_bank_owned_slice"
NEW_BENCH = "tb_starlink_pss_bank_arithmetic_actual"
OLD_SHADOW = "starlink_pss_payload_bubble_shadow"
NEW_SHADOW = "starlink_pss_bank_arithmetic_shadow"
RTL = ["starlink_pss_fft_bank_owned_arithmetic_probe", "starlink_pss_realtime_input_guard",
       "starlink_pss_realtime_result_guard", "starlink_pss_block_mailbox",
       "starlink_pss_forward_kernel_join", "starlink_pss_kernel_rom",
       "starlink_pss_spectrum_product_operand_register", "starlink_pss_spectrum_product_bank_arithmetic"]
TB = [NEW_BENCH + ".sv", NEW_SHADOW + ".sv", "starlink_pss_bank_arithmetic_actual_checks.svh",
      OLD_SHADOW + ".sv", "starlink_pss_forward_kernel_join_7ee87258_golden.v",
      "starlink_pss_kernel_rom_7ee87258_golden.v", "starlink_pss_spectrum_product_7ee87258_golden.v",
      "starlink_pss_realtime_result_guard_ce6a885e_golden.v", "starlink_pss_forward_retirement_shadow.sv"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def original(relative):
    return subprocess.run(["git", "-C", str(ROOT / "hdl"), "show",
                           f"{BASE}:library/starlink_pss_acquisition/{relative}"],
                          capture_output=True, text=True, check=True, timeout=15).stdout


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"nonunique strict adaptation anchor: {old[:100]}")
    return source.replace(old, new, 1)


def bench_edits():
    edits = [(f"module {OLD_BENCH};", f"module {NEW_BENCH};"),
             ("  parameter integer REGISTERED_SCHEDULING = 0;",
              "  parameter integer R = 1, B = 0, O = 0;\n  parameter integer REGISTERED_SCHEDULING = R;"),
             ("  starlink_pss_fft_bank_owned_slice #(.REGISTERED_SCHEDULING(REGISTERED_SCHEDULING)) dut (.*);",
              ("  starlink_pss_fft_bank_owned_arithmetic_probe #(.REGISTERED_SCHEDULING(REGISTERED_SCHEDULING),\n"
               "    .BOUNDARY_ROUND_SAT(B), .REGISTER_OPERANDS(O)) dut (.*);")),
             (f"  {OLD_SHADOW} payload_shadow (", f"  {NEW_SHADOW} #(.O(O)) payload_shadow ("),
             (f"  {OLD_SHADOW} forward_chain_shadow (", f"  {NEW_SHADOW} #(.O(O)) forward_chain_shadow (")]
    for instance in ("payload_shadow", "forward_chain_shadow"):
        # Same exact old public ports; only private state moved below the wrapper.
        old = ".product_private({dut.product.product_valid, dut.product.product_ii, dut.product.product_qq,\n      dut.product.product_iq, dut.product.product_qi})"
        new = old.replace("dut.product.", "dut.product.arithmetic.")
        # These two literal blocks intentionally use a context-local transform.
        edits.append((instance + "_PRIVATE", (old, new)))
    edits += [("  reg [31:0] samples [0:1405];", "  `include \"starlink_pss_bank_arithmetic_actual_checks.svh\"\n  reg [31:0] samples [0:1405];"),
              ("    $fclose(trace); $finish;", "    arithmetic_final_receipt();\n    $fclose(trace); $finish;")]
    return edits


def adapt_bench(source, inverse=False):
    edits = bench_edits()
    for old, new in reversed(edits) if inverse else edits:
        if old.endswith("_PRIVATE"):
            instance = old[:-8]
            start = source.index(" " + instance + " (")
            end = source.index("\n  );", start)
            before, after = new
            block = source[start:end]
            source = source[:start] + once(block, after if inverse else before,
                                           before if inverse else after) + source[end:]
        else:
            source = once(source, new if inverse else old, old if inverse else new)
    return source


ELASTIC_SLOT = """  // Independent reference token slot: four separately typed operands and
  // metadata, driven only by the frozen old joiner. Never sample DUT payload.
  reg occupied = 0;
  reg [17:0] a = 0, b = 0, c = 0, d = 0;
  reg [8:0] position = 0;
  reg [4:0] exponent = 0;
  reg last = 0;
  reg [63:0] start = 0;
  wire available = !occupied || p_ready;
  always @(posedge clk) begin
    if (!resetn || flush) begin
      occupied <= 0; a <= 0; b <= 0; c <= 0; d <= 0;
      position <= 0; exponent <= 0; last <= 0; start <= 0;
    end else if (available) begin
      occupied <= j_valid && product_enable;
      if (j_valid && product_enable) begin
        a <= j_i; b <= j_q; c <= j_ki; d <= j_kq;
        position <= j_position; exponent <= j_exponent;
        last <= j_last; start <= j_start;
      end
    end
  end
"""


def elastic_shadow(source):
    source = once(source, f"module {OLD_SHADOW}", f"module {NEW_SHADOW}_elastic")
    source = once(source, "  starlink_pss_forward_kernel_join_7ee87258_golden #(",
                  ELASTIC_SLOT + "  starlink_pss_forward_kernel_join_7ee87258_golden #(")
    source = once(source, ".output_valid(j_valid), .output_ready(p_ready)",
                  ".output_valid(j_valid), .output_ready(available && resetn && !flush)")
    source = once(source, ".input_valid(j_valid && product_enable)", ".input_valid(occupied)")
    source = once(source, ".input_ready(p_ready), .input_i(j_i), .input_q(j_q), .kernel_i(j_ki), .kernel_q(j_kq),\n    .input_bin_index(j_position), .input_block_exponent(j_exponent), .input_last(j_last),\n    .input_block_start_index(j_start)",
                  ".input_ready(p_ready), .input_i(a), .input_q(b), .kernel_i(c), .kernel_q(d),\n    .input_bin_index(position), .input_block_exponent(exponent), .input_last(last),\n    .input_block_start_index(start)")
    return once(source, "product_outputs !== {p_ready, p_valid", "product_outputs !== {(available && resetn && !flush), p_valid")


def shadow_source(old):
    header = old[old.index("module "):old.index("  wire j_ready")]
    header = once(header, f"module {OLD_SHADOW} #(\n", f"module {NEW_SHADOW} #(\n  parameter integer O = 0,\n")
    header = re.sub(r"output integer (\w+) = 0", r"output wire [31:0] \1", header)
    return ("`timescale 1ns/1fs\n// O0 binds the entire unchanged old shadow; O1 is an independent elastic reference.\n" + header +
            "  initial if (O !== 0 && O !== 1) $fatal(1, \"ARITHMETIC_SHADOW_OPTION_INVALID\");\n"
            "  generate if (O == 0) begin : unchanged_reference\n"
            f"    {OLD_SHADOW} #(.KERNEL_ROM_FILE(KERNEL_ROM_FILE)) reference (.*);\n"
            "  end else begin : extra_token_reference\n"
            f"    {NEW_SHADOW}_elastic #(.KERNEL_ROM_FILE(KERNEL_ROM_FILE)) reference (.*);\n"
            "  end endgenerate\nendmodule\n\n" + elastic_shadow(old))


def verify_adaptations():
    old = original(f"tb/{OLD_BENCH}.sv")
    current = (ACQ / "tb" / f"{NEW_BENCH}.sv").read_text()
    if adapt_bench(current, inverse=True) != old or (ACQ / "tb" / f"{OLD_BENCH}.sv").read_text() != old:
        raise ValueError("derived bench no longer restores all original checks")
    old_shadow = original(f"tb/{OLD_SHADOW}.sv")
    if (ACQ / "tb" / f"{OLD_SHADOW}.sv").read_text() != old_shadow:
        raise ValueError("original full reference changed")
    if (ACQ / "tb" / f"{NEW_SHADOW}.sv").read_text() != shadow_source(old_shadow):
        raise ValueError("independent elastic reference adaptation changed")
    if sha(ACQ / "create_shared_realtime_xfft_ip.tcl") != IP_SHA:
        raise ValueError("immutable actual generated FFT configuration changed")


def words(path, count):
    text = Path(path).read_text().splitlines()
    if len(text) != count or any(not re.fullmatch(r"[0-9a-fA-F]+", value) for value in text):
        raise ValueError("malformed frozen vector")
    return [int(value, 16) for value in text]


def unpack(word, width):
    mask, sign = (1 << width) - 1, 1 << (width - 1)
    return tuple(((word >> shift) & mask ^ sign) - sign for shift in (0, width))


def score(correlation, ef, ei, source):
    i, q = unpack(correlation, 18)
    energy = sum(i*i + q*q for i, q in (unpack(w, 16) for w in source))
    if len(source) != 66 or not energy:
        raise ValueError("score aperture/energy mismatch")
    numerator = min((i*i + q*q) << (2 * (7 + ef + ei)), (1 << 69) - 1)
    denominator = energy * 1073742825
    quotient, remainder = divmod(numerator * 255, denominator)
    result = min(255, quotient + (2*remainder > denominator or (2*remainder == denominator and quotient % 2)))
    return result


def product(a, b):
    ai, aq = unpack(a, 18)
    bi, bq = unpack(b, 18)
    result = []
    for value in (ai*bi-aq*bq, ai*bq+aq*bi):
        quotient, remainder = divmod(value, 1 << 18)
        quotient += remainder > (1 << 17) or (remainder == (1 << 17) and quotient % 2)
        if not -(1 << 17) <= quotient < (1 << 17):
            raise ValueError("frozen reference product overflow")
        result.append(quotient & ((1 << 18)-1))
    return result[0] | (result[1] << 18)


def verify_vectors(directory):
    directory = Path(directory)
    if {name: sha(directory / name) for name in VECTOR_HASHES} != VECTOR_HASHES:
        raise ValueError("immutable numerical source/cohort mismatch")
    samples = words(directory / "samples_ci16.mem", 1406)
    coefficients = samples[100:166]
    if coefficients != samples[447:513] or coefficients != samples[1000:1066] or \
            sum(i*i+q*q for i, q in (unpack(w, 16) for w in coefficients)) != 1073742825:
        raise ValueError("source PSS controls/coefficient energy mismatch")
    forward = words(directory / "forward_q17.mem", 1536)
    kernel = words(directory / "upper_edge_pss_kernel_q17.mem", 512)
    if [product(word, kernel[index % 512]) for index, word in enumerate(forward)] != words(directory / "product_q17.mem", 1536):
        raise ValueError("independent full spectrum-product oracle mismatch")
    inverse = words(directory / "inverse_q17.mem", 1536)
    ef = words(directory / "forward_exponents.mem", 3)
    ei = words(directory / "inverse_exponents.mem", 3)
    expected = words(directory / "scores_u8.mem", 1341)
    actual = [score(inverse[b*512+p+65], ef[b], ei[b], samples[b*447+p:b*447+p+66])
              for b in range(3) for p in range(447)]
    if actual != expected or any(expected[p] != 255 for p in (100, 447, 1000)):
        raise ValueError("independent inverse/source sample-score oracle mismatch")
    return {"scores": 1341, "independent_spectrum_products": 1536,
            "coefficient_energy": 1073742825, "score_scope": "oracle_only_no_scorer_RTL",
            "exponents_forward": ef, "exponents_inverse": ei}


def reject_synthetic(payloads):
    for name, payload in payloads.items():
        if not name.endswith((".v", ".sv", ".svh")):
            continue
        source = payload.decode()
        if "OFFLINE_NOT_FFT" in source or re.search(r"\bmodule\s+starlink_pss_fft512_bfp18_rt_candidate\b", source):
            raise ValueError("synthetic FFT module forbidden in actual source closure")


def freeze(output, vectors, frequency, r, b, o):
    output, vectors = Path(output).resolve(), Path(vectors).resolve()
    if frequency not in (175, 200) or (r, b, o) not in ((1, 0, 0), (1, 1, 1)):
        raise ValueError("only declared R1 baseline/candidate actual matrix")
    if output.exists():
        raise ValueError("refusing to overwrite any preparation/evidence")
    verify_adaptations()
    oracle = verify_vectors(vectors)
    paths = [ACQ / (name + ".v") for name in RTL] + [ACQ / "tb" / name for name in TB]
    paths += [ACQ / "create_shared_realtime_xfft_ip.tcl", ACQ / "simulate_bank_arithmetic_actual.tcl"]
    payloads = {path.name: path.read_bytes() for path in paths}
    if len(payloads) != len(paths):
        raise ValueError("source filename collision")
    payloads.update({name: (vectors / name).read_bytes() for name in VECTOR_HASHES})
    compiled = [name + ".v" for name in RTL] + [name for name in TB if not name.endswith(".svh")]
    payloads["profile.tcl"] = (f"set fast_mhz {frequency}\nset R {r}\nset B {b}\nset O {o}\n"
        + "set compiled_names {" + " ".join(compiled) + "}\n"
        + "set vector_names {" + " ".join(VECTOR_HASHES) + "}\n").encode()
    # Freeze the original derivation inputs as references, never compile them as DUT.
    payloads[OLD_BENCH + ".sv.reference"] = original("tb/" + OLD_BENCH + ".sv").encode()
    payloads["simulate_fft_bank_owned_slice.tcl.reference"] = original("simulate_fft_bank_owned_slice.tcl").encode()
    python_sources = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.suffix == ".py" and ROOT in path.parents:
            python_sources[path.relative_to(ROOT).as_posix()] = path
    for relative in ("tests/test_starlink_bank_arithmetic_actual_policy.py",):
        python_sources[relative] = ROOT / relative
    # Executable standalone copy avoids importing a mutable package after freeze.
    payloads["bank_arithmetic_actual.py"] = Path(__file__).read_bytes()
    for relative, path in python_sources.items():
        payloads["python__" + relative.replace("/", "__")] = path.read_bytes()
    reject_synthetic(payloads)
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in payloads.items()}
    source = output / "frozen_sources"
    source.mkdir(parents=True)
    for name, payload in payloads.items():
        (source / name).write_bytes(payload)
    manifest = {"schema": "bank-arithmetic-actual-preparation-v1", "frequency": frequency,
                "R": r, "B": b, "O": o, "base_hdl": BASE, "actual_run": False,
                "source_sha256": hashes, "python_import_sources": sorted(python_sources),
                "rtl": [name + ".v" for name in RTL], "tb": TB, "vectors": list(VECTOR_HASHES),
                "original_r1_complete_csv_sha256": HISTORICAL_R1_CSV,
                "baseline_complete_csv_match_required": frequency == 175 and b == o == 0,
                "unchanged_bounds": OLD_BOUNDS, "normal_R1_core_job": CORE_TIMING,
                "oracle": oracle, "no_FFT_simulation_or_physical_run_during_preparation": True}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    verify_freeze(output)
    return manifest


def verify_freeze(output):
    output = Path(output).resolve()
    manifest = json.loads((output / "manifest.json").read_text())
    source = output / "frozen_sources"
    actual = {p.name: sha(p) for p in source.iterdir() if p.is_file() and not p.is_symlink()}
    if len(list(source.iterdir())) != len(actual) or actual != manifest["source_sha256"]:
        raise ValueError("complete frozen source inventory/hash mismatch")
    if actual.get("create_shared_realtime_xfft_ip.tcl") != IP_SHA:
        raise ValueError("wrong generated FFT configuration")
    if manifest.get("schema") != "bank-arithmetic-actual-preparation-v1" or manifest.get("base_hdl") != BASE or \
            manifest.get("frequency") not in (175, 200) or (manifest.get("R"), manifest.get("B"), manifest.get("O")) not in ((1, 0, 0), (1, 1, 1)):
        raise ValueError("frozen declared profile mismatch")
    expected_profile = f"set fast_mhz {manifest['frequency']}\nset R {manifest['R']}\nset B {manifest['B']}\nset O {manifest['O']}\n"
    if not (source / "profile.tcl").read_text().startswith(expected_profile):
        raise ValueError("manifest and actual Tcl profile differ")
    if manifest.get("original_r1_complete_csv_sha256") != HISTORICAL_R1_CSV or \
            manifest.get("baseline_complete_csv_match_required") != (manifest["frequency"] == 175 and manifest["B"] == manifest["O"] == 0):
        raise ValueError("historical baseline CSV policy changed")
    if manifest.get("unchanged_bounds") != OLD_BOUNDS or manifest.get("normal_R1_core_job") != CORE_TIMING:
        raise ValueError("original fault/latency bounds changed")
    reject_synthetic({p.name: p.read_bytes() for p in source.iterdir()})
    verify_vectors(source)
    return manifest


def require_terminal(log, manifest):
    if re.search(r"FAIL|MISMATCH|FATAL|ERROR", log, re.IGNORECASE):
        raise ValueError("late or early simulation failure overrides every PASS")
    required = ["FFT_BANK_OWNED_SLICE_PASS", "COMPLETED_INPUT_ACTUAL_CORE_EQ_PASS",
                "RAW_READY_CERTIFIED_ACK_PASS", "REGISTERED_SCHEDULING_PASS",
                "PREFLIGHT_REASON_SPLIT_PASS", "HELD_PHASE_INPUT_PASS", "BALANCED_IDENTITY_ACTUAL_PASS",
                "HELD_PREFLIGHT_ACTUAL_PASS", "PAYLOAD_BUBBLES_ACTUAL_PASS", "FORWARD_RETIREMENT_ACTUAL_PASS",
                "BANK_ARITHMETIC_ACTUAL_PASS"]
    rows = {}
    for marker in required:
        matches = re.findall(r"^" + marker + r" (.*)$", log, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError(f"missing/duplicate complete terminal marker {marker}")
        rows[marker] = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", matches[0])}
    final = rows["BANK_ARITHMETIC_ACTUAL_PASS"]
    expected = {key: manifest[key] for key in ("R", "B", "O")}
    expected.update(fast_mhz=manifest["frequency"], exact_event_words_per_stream=19456,
                    nominal_blocks=32, stalled_blocks=6, latency_checks=32,
                    accept_to_bank_clocks=3+manifest["O"], old_fault_checks_unchanged=1, score_oracle_only=1)
    if final != expected:
        raise ValueError("actual instance/event/latency terminal contract mismatch")
    base = rows["FFT_BANK_OWNED_SLICE_PASS"]
    if any(base.get(k) != v for k, v in {"fast_mhz": manifest["frequency"], "healthy_blocks": 44,
                                        "purge_cases": 4, "fault_cases": 10}.items()):
        raise ValueError("original complete nominal/reset/fault contract mismatch")
    prefix = base.get("provisional_prefix_words", -1)
    if not 128 <= prefix <= 132 or base.get("inverse_words") != 44*512+prefix:
        raise ValueError("original provisional-prefix contract mismatch")
    if any(base.get(k, 0) <= 0 for k in ("overlap_loads", "acceptance_equality_witnesses",
               "closed_input_prefetch_witnesses", "held_final_ready_witnesses")):
        raise ValueError("missing original ownership witness")
    exact = {
        "RAW_READY_CERTIFIED_ACK_PASS": {"handoff_fault_cases": 11, "late_ack_witnesses": 4, "handoff_reset_recovery": 1},
        "REGISTERED_SCHEDULING_PASS": {"boundary_fault_cases": 8, "boundary_reset_cases": 4, "snapshot_to_admission_cycles": 2},
        "PREFLIGHT_REASON_SPLIT_PASS": {"matrix_cases": 84, "transform_phases": 2, "reason_bits": 6, "one_sided_fault_recoveries": 2},
        "HELD_PHASE_INPUT_PASS": {"registered": 1, "active_fault_cases": 12, "vendor_open_quarantine_cases": 2, "reset_recoveries": 2},
        "BALANCED_IDENTITY_ACTUAL_PASS": {"enabled": 1, "exact_per_beat_fault_reasons": 1},
        "HELD_PREFLIGHT_ACTUAL_PASS": {"registered": 1, "expected_cache_cases": 12, "raw_bank_boundary_rows": 84},
        "PAYLOAD_BUBBLES_ACTUAL_PASS": {"registered": 1, "frozen_old_chain": 1},
        "FORWARD_RETIREMENT_ACTUAL_PASS": {"registered": 1, "all_old_outputs_literal": 1},
    }
    for marker, values in exact.items():
        if any(rows[marker].get(key) != value for key, value in values.items()):
            raise ValueError("incomplete original late control/fault matrix")
    return rows


def verify_events(path, vectors):
    vectors = Path(vectors)
    samples = words(vectors / "samples_ci16.mem", 1406)
    references = {kind: words(vectors / (kind + "_q17.mem"), 1536) for kind in ("forward", "product", "inverse")}
    ef = words(vectors / "forward_exponents.mem", 3)
    ei = words(vectors / "inverse_exponents.mem", 3)
    scores = words(vectors / "scores_u8.mem", 1341)
    counts = {(epoch, kind): 0 for epoch in (1, 2) for kind in references}
    last_cycles = dict.fromkeys(counts, -1)
    score_count = 0
    with Path(path).open() as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["epoch", "stream", "ordinal", "data", "position", "last", "start", "ef", "ei", "cycle"]:
            raise ValueError("event schema mismatch")
        for row in reader:
            try:
                kind = row.pop("stream")
                value = int(row.pop("data"), 16)
                row = {key: int(value) for key, value in row.items()}
                key = row["epoch"], kind
                ordinal = counts[key]
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError("unknown/malformed event") from exc
            block, position = divmod(ordinal, 512)
            fixture = block % 3
            if row != {"epoch": key[0], "ordinal": ordinal, "position": position, "last": int(position == 511),
                       "start": 0x200000000 + key[0]*65536 + block*447,
                       "ef": ef[fixture], "ei": ei[fixture] if kind == "inverse" else 0,
                       "cycle": row["cycle"]} or row["cycle"] <= last_cycles[key]:
                raise ValueError("independent ordered event identity/exponent/position mismatch")
            if value != references[kind][fixture*512+position]:
                raise ValueError("event exact numerical mismatch")
            if kind == "inverse" and position >= 65:
                index = fixture*447+position-65
                if score(value, row["ef"], row["ei"], samples[index:index+66]) != scores[index]:
                    raise ValueError("actual inverse/source sample-score oracle mismatch")
                score_count += 1
            counts[key] += 1
            last_cycles[key] = row["cycle"]
    if any(count != (32 if epoch == 1 else 6)*512 for (epoch, _), count in counts.items()) or score_count != 38*447:
        raise ValueError("incomplete event or score oracle stream")
    return {"ordered_words_per_stream": 19456, "output_derived_exact_sample_scores": score_count,
            "score_scope": "oracle_only_no_scorer_RTL", "events_sha256": sha(path)}


def verify_results(output):
    output = Path(output).resolve()
    manifest = verify_freeze(output)
    started = (output / "launch_started.txt").read_text()
    expected_start = f"actual_fft=true R={manifest['R']} B={manifest['B']} O={manifest['O']} frequency={manifest['frequency']} no_restart=true\n"
    if started != expected_start:
        raise ValueError("missing actual source-specific launch receipt")
    before = (output / "generated_ip_before.txt").read_text()
    after = (output / "generated_ip_after.txt").read_text()
    match = re.fullmatch(r"([0-9a-f]{64})  ([^\n]+)\n", before)
    if not match or before != after:
        raise ValueError("generated FFT source pre/post receipt mismatch")
    wrapper = Path(match[2]).resolve()
    if output not in wrapper.parents or sha(wrapper) != match[1]:
        raise ValueError("generated FFT source identity mismatch")
    simulation = output / "project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim"
    log_path = simulation / "simulate.log"
    log = log_path.read_text()
    receipts = require_terminal(log, manifest)
    trace = simulation / "fft_bank_owned_trace.csv"
    if manifest["baseline_complete_csv_match_required"] and sha(trace) != HISTORICAL_R1_CSV:
        raise ValueError("R1/B0/O0 complete historical baseline CSV changed")
    # Nominal and repeated-stall job service expectations come from dec20 R1,
    # never the earlier R0 1809-cycle service or a post-hoc candidate retiming.
    jobs = re.findall(r"^BANK_JOB (.*)$", log, re.MULTILINE)
    selected = [{k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", line)} for line in jobs]
    selected = [row for row in selected if row["epoch"] in (1, 2)]
    if len(selected) != 76 or any(any(row.get(k) != v for k, v in manifest["normal_R1_core_job"].items()) for row in selected):
        raise ValueError("immutable real FFT nominal service changed")
    events = verify_events(simulation / "bank_arithmetic_events.csv", output / "frozen_sources")
    return {"schema": "bank-arithmetic-actual-results-v1", "actual_run": True,
            "R": manifest["R"], "B": manifest["B"], "O": manifest["O"], "frequency": manifest["frequency"],
            "receipts": receipts, "events": events, "trace_sha256": sha(trace), "log_sha256": sha(log_path),
            "historical_baseline_trace_match_required": manifest["baseline_complete_csv_match_required"],
            "scorer_RTL_or_physical_or_RF_qualified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify", "results"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--vectors", type=Path)
    parser.add_argument("--fast-mhz", type=int, default=175)
    parser.add_argument("--R", type=int, default=1)
    parser.add_argument("--B", type=int, default=0)
    parser.add_argument("--O", type=int, default=0)
    args = parser.parse_args()
    if args.mode == "prepare":
        result = freeze(args.output, args.vectors, args.fast_mhz, args.R, args.B, args.O)
    elif args.mode == "verify":
        result = verify_freeze(args.output)
    else:
        result = verify_results(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
