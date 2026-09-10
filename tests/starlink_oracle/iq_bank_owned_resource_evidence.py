"""Freeze complete coarse OOC synthesis resources, never timing qualification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .iq_bank_owned_evidence import REQUIRED_COMMON_FILES, digest, parse_run


def hierarchy_rows(text: str) -> list[dict]:
    result = []
    for line in text.splitlines():
        columns = [column.strip() for column in line.split("|")[1:-1]]
        if len(columns) == 10 and all(value.isdecimal() for value in columns[2:]):
            result.append(
                dict(
                    zip(
                        [
                            "instance",
                            "module",
                            "total_luts",
                            "logic_luts",
                            "lutram",
                            "srl",
                            "flip_flops",
                            "ramb36",
                            "ramb18",
                            "dsp",
                        ],
                        columns[:2] + [int(value) for value in columns[2:]],
                        strict=True,
                    )
                )
            )
    return result


def collect(directory: Path, simulation: Path) -> dict:
    prior = parse_run(simulation, "numeric", 200, "exact")
    log = directory / (directory.name + ".log")
    terminal = "BANK_IQ_TO_SCORE_COMPLETE_COARSE_SYNTHESIS_RESOURCES_RECORDED"
    if log.read_text().splitlines().count(terminal) != 1:
        raise ValueError("missing unique complete coarse synthesis terminal")
    scope = (directory / "scope.txt").read_text()
    inherited = {name for name in REQUIRED_COMMON_FILES if name.endswith(".v")} | {
        "create_shared_realtime_xfft_ip.tcl",
        "upper_edge_pss_kernel_q17.mem",
    }
    expected = inherited | {
        "synthesize_iq_to_score_bank_owned.tcl",
        "fft_bank_owned_synth_threads.tcl",
        "fft_bank_owned_resource_probe.xdc",
    }
    sources = {
        path.name: digest(path) for path in (directory / "frozen_sources").iterdir()
    }
    if set(sources) != expected:
        raise ValueError("incomplete or extra coarse synthesis frozen inventory")
    for name, sha in sources.items():
        if f"{sha}  {directory / 'frozen_sources' / name}" not in scope:
            raise ValueError("synthesis source changed after pre-run freeze")
        if name in inherited and sha != prior["frozen_source_sha256"][name]:
            raise ValueError("synthesis differs from passed actual-core simulation")
    wrapper = (
        directory / "project/iq_bank_owned_synthesis.gen/sources_1/ip/"
        "starlink_pss_fft512_bfp18_rt_candidate/synth/starlink_pss_fft512_bfp18_rt_candidate.vhd"
    )
    if (
        f"{digest(wrapper)}  {wrapper}" not in scope
        or digest(wrapper) != prior["generated_bench_core_sha256"][wrapper.name]
    ):
        raise ValueError("generated FFT differs from original measured contract")
    receipt = (directory / "resource_receipt.txt").read_text()
    if "black_boxes=0" not in receipt or "synthesis_only=true" not in receipt:
        raise ValueError("incomplete synthesis or black-box resource estimate")
    hierarchy = hierarchy_rows((directory / "hierarchy.rpt").read_text())
    totals = [
        row
        for row in hierarchy
        if row["instance"] == "starlink_pss_iq_to_score_bank_owned"
    ]
    if len(totals) != 1 or not {
        "scheduler",
        "energy_cache",
        "candidate_score_path",
        "island",
        "shared_xfft",
        "source_bank",
        "product_bank",
        "output_bank",
    } <= {row["instance"] for row in hierarchy}:
        raise ValueError("missing complete coarse hierarchy")
    total = totals[0]
    for key, label in (
        ("dsp", "dsp48e1"),
        ("ramb18", "ramb18e1"),
        ("ramb36", "ramb36e1"),
    ):
        if f"{label}={total[key]}" not in receipt.splitlines():
            raise ValueError("hierarchy and primitive inventory disagree")
    report_names = [
        "utilization.rpt",
        "hierarchy.rpt",
        "synthesis_clocks.rpt",
        "check_timing_unqualified.rpt",
        "cdc_unqualified.rpt",
        "resource_receipt.txt",
        "scope.txt",
    ]
    return {
        "scope": "complete coarse actual-core OOC synthesis only; unplaced and unrouted; not receiver resource saving",
        "artifact_directory": str(directory),
        "source_simulation": str(simulation),
        "source_simulation_log_sha256": prior["simulate_log_sha256"],
        "frozen_source_sha256": sources,
        "generated_fft_sha256": digest(wrapper),
        "terminal_receipt": terminal,
        "top_log_sha256": digest(log),
        "dcp_sha256": digest(directory / "iq_bank_owned_synth.dcp"),
        "totals": total,
        "bram_36k_tiles": total["ramb36"] + total["ramb18"] / 2,
        "hierarchy": hierarchy,
        "reports": {
            name: {
                "sha256": digest(directory / name),
                "text": (directory / name).read_text(),
            }
            for name in report_names
        },
        "qualified_clock_or_full_receiver_area_saving": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("simulation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(
            collect(args.directory.resolve(), args.simulation.resolve()), indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
