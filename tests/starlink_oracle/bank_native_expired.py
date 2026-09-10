"""Expected events for one expired public-native command, not a packet oracle.

The approved synthetic520 numerical cohort is read-only. This contract describes
the scheduler's first-request late branch and public empty-result observations;
it never supplies fabricated RTL counters or result words.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import bank_native_true_pss as healthy

PROFILE = "520-pss-expired"
REQUEST = 0x15005202
FIXTURE_SHA256 = "aa4330480879e5f44abdfeb34b5ddeca098f1b22352715743f0db32e6672de81"
FILES = ("native_expired_registers.mem", "native_expired_contract.json")
PYTHON_DEPENDENCIES = (*healthy.PYTHON_DEPENDENCIES, "tests/starlink_oracle/bank_native_expired.py")


def public_registers() -> list[tuple[int, int]]:
    return [(0x38, 0), (0x3C, 0), (0x80, 0),
            *((0x84 + 4 * n, int(n in (2, 3))) for n in range(14)),
            *((address, 0) for address in range(0xBC, 0xE4, 4)),
            (0x4C, healthy.GENERATION), (0x5C, 0x1A000000),
            (0x60, healthy.ENERGY), (0x64, 0)]


def derive() -> tuple[dict[str, bytes], dict]:
    registers = public_registers()
    payload = healthy.words((word for pair in registers for word in pair), 8)
    root = Path(__file__).resolve().parents[2]
    manifest = {
        "schema": "bank-native-expired-event-contract-v1", "profile": PROFILE,
        "scope": "one late native request; coarse/pilot healthy; NOT a healthy native visit or causal acquisition",
        "unchanged_cohort_fixture_sha256": FIXTURE_SHA256,
        "request_id": REQUEST, "coefficient_generation": healthy.GENERATION,
        "center_index": healthy.CENTER, "capture_bounds": [healthy.CENTER - 32, healthy.CENTER + 98],
        "public_submit_source_offset_bounds_inclusive": [620, 624],
        "scheduler_handshake_source_offset_bounds_inclusive": [620, 640],
        "minimum_lead_samples": 64,
        "late_predicate": "unsigned64(start-(accepted_index+1)); signbit1 OR lead<64",
        "required_rejection_priority": "duplicate0, overlap0, late1 on first consecutive enabled command handshake",
        "expected_public_submits": 1, "expected_wrapper_handshakes": 1,
        "expected_fifo_accept_pulses": 1, "expected_sample_handshakes": 1,
        "expected_admitted": 0, "expected_rejected": 1, "expected_late": 1,
        "expected_capture_words": 0, "expected_completed_capture": 0,
        "expected_result_packets": 0, "expected_IRQ": 0,
        "empty_result_contract": "public0x5c=0x1a000000 and status0x14 bits7:6=0; do not read unavailable0x54",
        "public_registers_per_snapshot": len(registers), "atomic_snapshot_generations": [1, 2],
        "public_registers": [{"address": address, "value": value} for address, value in registers],
        "coarse_scores": 894, "map_words": 447, "pilot_words": 512, "pilot_bytes": 2048,
        "concurrency": "bounded public-submit through sample-rejection window; positive fft_clk RUN_JOB and100MHz pilot-DDC accepts; first fft edge after sample handshake also RUN_JOB",
        "generated_sha256": {FILES[0]: healthy.sha(payload)},
        "python_runtime_sha256": {name: healthy.digest(root / name) for name in PYTHON_DEPENDENCIES},
        "actual_RTL_qualified": False, "physical_RF_causal_qualified": False,
    }
    return {FILES[0]: payload, FILES[1]: healthy.json_bytes(manifest)}, manifest


def verify_cohort(score: Path, pilot: Path, native: Path) -> None:
    healthy.verify(score, pilot, native)
    if healthy.digest(score.resolve().parent / "fixture.json") != FIXTURE_SHA256:
        raise ValueError("expired profile requires the unchanged approved520-PSS cohort")


def generate(score: Path, pilot: Path, native: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ValueError("refusing to overwrite expired event evidence")
    verify_cohort(score, pilot, native)
    files, manifest = derive()
    output.mkdir(parents=True)
    for name, payload in files.items():
        (output / name).write_bytes(payload)
    return manifest


def verify(score: Path, pilot: Path, native: Path, output: Path) -> dict:
    verify_cohort(score, pilot, native)
    files, manifest = derive()
    if {path.name for path in output.iterdir()} != set(files) or any(
            not path.is_file() or path.is_symlink() for path in output.iterdir()):
        raise ValueError("expired event inventory mismatch")
    for name, expected in files.items():
        if (output / name).read_bytes() != expected:
            raise ValueError(f"expired event independent contract mismatch: {name}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "verify"))
    for name in ("score", "pilot", "native", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    (generate if args.command == "generate" else verify)(args.score, args.pilot, args.native, args.output)
    print("BANK_NATIVE_EXPIRED_ORACLE_VERIFIED profile=520-pss-expired request=15005202 rejected=1 late=1 admitted=0 packets=0 public_registers=31")
