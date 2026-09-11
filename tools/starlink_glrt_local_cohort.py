"""Combine revalidated GLA1 comparisons without assuming gaps between captures."""
from __future__ import annotations

import argparse
from pathlib import Path

from .starlink_glrt_abi import require
from .starlink_glrt_local_compare import (
    POLICY,
    canonical_digest,
    compare_capture,
    load,
    save,
)


def combine(reports):
    require(bool(reports), "requires at least one comparison")
    identities = [r["capture_sha256"]["iq.ci16"] for r in reports]
    require(len(set(identities)) == len(identities), "duplicate IQ cannot add reception evidence")
    require(all(r["schema"] == "gla1-same-window-comparison/v1" and r["status"] == "complete"
                and r["policy"] == POLICY for r in reports), "comparison policy differs")
    positives = sum(r["host_supported_windows"] for r in reports)
    recovered = sum(r["recovered_windows"] for r in reports)
    positive_runs = [r for r in reports if r["host_positive_episodes"]]
    # Without inter-capture time evidence, each adjacent pair might share one
    # episode. Deduct every possible boundary merge instead of inventing a gap.
    episodes = (sum(r["host_positive_episodes"] for r in positive_runs)
                - max(0, len(positive_runs) - 1))
    recovery = recovered / positives if positives else None
    sufficient = (positives >= POLICY["minimum_positive_windows"]
                  and episodes >= POLICY["minimum_positive_episodes"])
    extras = [{"capture_iq_sha256": identities[n], **row}
              for n, r in enumerate(reports) for row in r["fpga_additional_or_mismatched"]]
    gate = ("inconclusive" if not sufficient else "fail"
            if recovery < POLICY["minimum_supported_window_recovery"] else
            "review_required" if extras else "pass")
    return {"schema": "gla1-comparison-cohort/v1", "status": "complete", "detection_gate": gate,
            "policy": POLICY, "captures": len(reports), "capture_iq_sha256": identities,
            "comparison_sha256": [canonical_digest(r) for r in reports],
            "comparable_windows": sum(r["comparable_windows"] for r in reports),
            "host_supported_windows": positives, "recovered_windows": recovered,
            "recovery": recovery, "positive_episode_lower_bound": episodes,
            "inter_capture_gaps_assumed": False, "additional_detections": extras,
            "missing_completion_windows": sum(len(r["host_windows_without_fpga_completion"])
                                              for r in reports),
            "live_detector_qualified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", nargs=3, action="append", required=True,
                        metavar=("CAPTURE", "PLAN", "HOST_REPLAY"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports, configurations = [], []
    for capture, plan, host in args.run:
        reports.append(compare_capture(capture, plan, host))
        protocol = load(Path(capture) / "protocol.json")
        configurations.append({k: protocol[k] for k in (
            "serial", "firmware_version", "source_rate", "lo_hz", "bandwidth_hz", "edge")})
    require(all(c == configurations[0] for c in configurations), "capture radio/profile differs")
    result = combine(reports)
    result["configuration"] = configurations[0]
    save(args.output, result)


if __name__ == "__main__":
    main()
