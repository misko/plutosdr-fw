"""Bounded offline experiment; does not replace the frozen FFT contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.starlink_oracle import xfft_bitacc as fft
from tests.starlink_oracle.acquisition import direct_fixed_match_scores
from tests.starlink_oracle.ddc import conditioned_pss, conditioned_pss_x4
from tests.starlink_oracle.fixed import quantize_q15
from tests.starlink_oracle.waveforms import complex64_sha256, projected_pss

SCHEMA = "starlink-direct-coarse-evaluation-v1"
# Declared before executing the experiment. Failures are retained, never used
# to tune these gates. These are comparison gates, not RF detection criteria.
GATES = {"max_score_delta": 1, "peak_index_delta": 0}
PINS = {
    "firmware": "ec36b96965df76f83b80e70c1aba867e7cbbbc30",
    "hdl": "eb96c64738697c10b9c0abb379ab64f6a4a5c59c",
}
FROZEN = Path(
    "/home/mouse9911/gits/plutosdr-fw-starlink-rx-only/hdl/library/"
    "starlink_pss_raw_correlator/build/input-cursor-paired-v1/frozen_sources"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_mem(path: Path, bits: int) -> np.ndarray:
    words = [int(line, 16) for line in path.read_text().splitlines()]
    mask, sign = (1 << bits) - 1, 1 << (bits - 1)
    return np.array(
        [
            [
                (w & mask) - ((1 << bits) if w & sign else 0),
                ((w >> bits) & mask) - ((1 << bits) if (w >> bits) & sign else 0),
            ]
            for w in words
        ],
        dtype=np.int64,
    )


def direct_scores(samples: np.ndarray, h: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Exact vectorized integer products; normalization uses Python wide ints."""
    x, h = np.asarray(samples, np.int64), np.asarray(h, np.int64)
    count = len(x) - len(h) + 1
    re, im, ex = (np.zeros(count, np.int64) for _ in range(3))
    eh = int(np.sum(h * h))
    for k, (hi, hq) in enumerate(h):
        xi, xq = x[k : k + count].T
        re += xi * hi + xq * hq
        im += xq * hi - xi * hq
        ex += xi * xi + xq * xq
    scores = np.array(
        [
            fft._round_normalized_power(
                int(a) ** 2 + int(b) ** 2, int(e) * eh, full_scale=255
            )
            for a, b, e in zip(re, im, ex, strict=True)
        ],
        dtype=np.int16,
    )
    return scores, np.column_stack((re, im))


def float_scores(samples: np.ndarray, template: np.ndarray) -> np.ndarray:
    """Independent float-domain convolution with unquantized projected taps."""
    x = samples[:, 0].astype(float) + 1j * samples[:, 1]
    h = np.asarray(template, np.complex128)
    c = np.convolve(x, np.conj(h[::-1]), mode="valid")
    ex = np.convolve(np.abs(x) ** 2, np.ones(len(h)), mode="valid")
    p = np.divide(
        np.abs(c) ** 2, ex * np.sum(np.abs(h) ** 2), out=np.zeros(len(c)), where=ex > 0
    )
    return np.clip(np.rint(p * 255), 0, 255).astype(np.int16)


def compare(reference: np.ndarray, candidate: np.ndarray) -> dict:
    delta = candidate.astype(int) - reference.astype(int)
    bad = np.flatnonzero(np.abs(delta) > GATES["max_score_delta"])
    peak_delta = int(np.argmax(candidate)) - int(np.argmax(reference))
    return {
        "score_count": len(delta),
        "changed_scores": int(np.count_nonzero(delta)),
        "max_abs_score_delta": int(np.max(np.abs(delta))),
        "peak_index_delta": peak_delta,
        "reference_peak": int(np.argmax(reference)),
        "candidate_peak": int(np.argmax(candidate)),
        "comparison_pass": len(bad) == 0 and peak_delta == GATES["peak_index_delta"],
        "beyond_tolerance": [
            {
                "index": int(i),
                "reference": int(reference[i]),
                "candidate": int(candidate[i]),
            }
            for i in bad
        ],
    }


def tail_report(h: np.ndarray, kernel: np.ndarray) -> dict:
    # Template FFT has /4 scale. np.ifft supplies the transform's 1/512.
    impulse = np.fft.ifft((kernel[:, 0] + 1j * kernel[:, 1]) / 2**17) * 4
    ideal = np.zeros(512, complex)
    ideal[:66] = np.conj((h[:, 0] + 1j * h[:, 1])[::-1]) / 2**15
    tail = impulse[66:]
    return {
        "tap_count": len(h),
        "q15_sha256": hashlib.sha256(h.astype("<i2").tobytes()).hexdigest(),
        "kernel_i32le_sha256": hashlib.sha256(
            kernel.astype("<i4").tobytes()
        ).hexdigest(),
        "coefficient_energy": int(np.sum(h.astype(np.int64) ** 2)),
        "tail_nonzero_count_at_1e_minus_15": int(
            np.count_nonzero(np.abs(tail) > 1e-15)
        ),
        "tail_energy_fraction": float(
            np.sum(np.abs(tail) ** 2) / np.sum(np.abs(impulse) ** 2)
        ),
        "tail_energy_db": float(
            10 * np.log10(np.sum(np.abs(tail) ** 2) / np.sum(np.abs(impulse) ** 2))
        ),
        "maximum_tail_magnitude_q15_units": float(np.max(np.abs(tail)) * 2**15),
        "tail_l1_fullscale_complex_error_bound_ci16_q15": float(
            np.sum(np.abs(tail)) * math.sqrt(2) * 2**30
        ),
        "total_relative_impulse_l2_error": float(
            np.linalg.norm(impulse - ideal) / np.linalg.norm(ideal)
        ),
        "finite_66_tap_bit_equivalence": False,
    }


def schedule(
    clock: int,
    lanes: int,
    count: int = 100_000,
    stall_every: int = 0,
    stall_length: int = 0,
    depth: int = 128,
) -> dict:
    """Event model with ordered ADC arrivals and fixed-length issue jobs.

    Six logical read ports are supplied by six replicated 128x32 simple-dual-
    port memories; each clock also writes the newest sample in every replica.
    Same-address reads are not assumed safe. Occupancy includes 66 live taps.
    Stalls pause issue; pipeline drain/reduction overlaps the next job.
    """
    cycles_per_job = math.ceil(66 / lanes)
    next_free = 0
    max_backlog = 0
    expired = 0
    max_delay = 0
    for n in range(65, count):
        arrival = math.ceil((n + 1) * clock / 15_000_000)
        begin = max(arrival + 1, next_free)  # avoid read/write collision
        end = begin + cycles_per_job
        # An explicit output stall after each Nth completed issue job.
        if stall_every and (n - 64) % stall_every == 0:
            end += stall_length
        next_free = end
        # Conservative whole-window lifetime until final issue completes.
        newest = min(count - 1, (end * 15_000_000) // clock - 1)
        oldest = n - 65
        backlog = newest - n
        max_backlog = max(max_backlog, backlog)
        max_delay = max(max_delay, end - arrival)
        expired += newest - oldest >= depth
    return {
        "clock_hz": clock,
        "lanes": lanes,
        "issue_cycles": cycles_per_job,
        "ideal_outputs_per_second": clock / cycles_per_job,
        "samples": count,
        "max_backlog_samples": max_backlog,
        "memory_depth_per_replica": depth,
        "expired_jobs": expired,
        "max_job_delay_clocks": max_delay,
        "stall_every_jobs": stall_every,
        "stall_length_clocks": stall_length,
        "bounded_for_test": expired == 0 and max_backlog < depth - 66,
    }


def run(output: Path, frozen: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    fft.XFFT_DATA_BITS, fft.XFFT_FRACTION_BITS = 18, 17
    model_dir = fft.prepare_installed_cmodel(output / "cmodel")
    reports, cases = {}, []
    rng = np.random.default_rng(0x66C0A25E)
    templates = {
        (rate, edge): (
            projected_pss(15_000_000, edge)
            if rate == 15
            else conditioned_pss(edge)
            if rate == 30
            else conditioned_pss_x4(edge)
        )
        for rate in (15, 30, 60)
        for edge in ("upper", "lower")
    }
    with fft.XfftBitAccModel(model_dir) as model:
        for (rate, edge), template in templates.items():
            h = quantize_q15(template).astype(np.int64)
            kernel = fft._template_kernel(h, model)
            report = tail_report(h, kernel)
            report["float_template_sha256"] = complex64_sha256(template)
            if edge == "upper":
                name = {
                    15: "upper_edge_pss_kernel_q17.mem",
                    30: "upper_edge_pss30_x2_ddc_kernel_q17.mem",
                    60: "upper_edge_pss60_x4_ddc_kernel_q17.mem",
                }[rate]
                path = ROOT / "hdl/library/starlink_pss_acquisition/tb" / name
                assert np.array_equal(kernel, read_mem(path, 18)), name
                report["existing_kernel_mem_sha256"] = digest(path)
            reports[f"source{rate}_{edge}"] = report
        # Independent immutable current FFT golden, never rewritten.
        frozen_metadata = json.loads((frozen / "paired_oracle.json").read_text())
        frozen_files = [
            "samples_ci16",
            "scores_u8",
            "forward_exponents",
            "inverse_exponents",
        ]
        for name in frozen_files:
            assert (
                digest(frozen / f"{name}.mem")
                == frozen_metadata["score_vector_sha256"][name]
            )
        x = read_mem(frozen / "samples_ci16.mem", 16)
        h = quantize_q15(templates[(15, "upper")])
        golden = np.array(
            [int(v, 16) for v in (frozen / "scores_u8.mem").read_text().splitlines()]
        )
        current = fft.xfft_bitacc_match_scores(x, h, model)
        assert np.array_equal(current.stream.scores, golden)
        assert list(current.forward_block_exponents) == [
            int(v, 16)
            for v in (frozen / "forward_exponents.mem").read_text().splitlines()
        ]
        assert list(current.inverse_block_exponents) == [
            int(v, 16)
            for v in (frozen / "inverse_exponents.mem").read_text().splitlines()
        ]
        direct, _ = direct_scores(x, h)
        assert np.array_equal(direct, direct_fixed_match_scores(x, h).scores)
        golden_comparison = compare(golden, direct)
        for edge in ("upper", "lower"):
            template = templates[(15, edge)]
            h = quantize_q15(template)
            specs = [
                (str(cfo), cfo, snr, start, False)
                for cfo in (-1_200_000, -100_000, 0, 100_000, 1_200_000)
                for snr in (-12, 0, 12)
                for start in (0, 447, 959)
            ]
            specs += [
                ("noise_only", 0, None, None, False),
                ("zero", 0, None, None, False),
                ("clipped", 0, 12, 447, True),
                ("signed_endpoints", 0, None, None, False),
                ("isolated_fullscale_impulse", 0, None, None, False),
                ("nearzero_remote_fullscale", 0, None, None, False),
            ]
            for label, cfo, snr, start, clipped in specs:
                # Extra dynamic-range probes have a separate RNG so all 98
                # initial comparison inputs retain their original identities.
                case_rng = np.random.default_rng(66400) if "fullscale" in label else rng
                xfloat = (
                    case_rng.normal(size=1536) + 1j * case_rng.normal(size=1536)
                ) * 1000
                if start is not None:
                    # SNR is mean per complex sample over the 66-sample PSS.
                    amplitude = math.sqrt(66 * 2 * 1000**2 * 10 ** (snr / 10))
                    if clipped:
                        amplitude *= 40
                    phase = np.exp(2j * np.pi * cfo * np.arange(66) / 15_000_000)
                    xfloat[start : start + 66] += amplitude * template * phase
                if label == "zero":
                    xfloat[:] = 0
                if label == "isolated_fullscale_impulse":
                    xfloat[:] = 0
                    xfloat[400] = 32767 - 32768j
                if label == "nearzero_remote_fullscale":
                    xfloat /= 1000
                    xfloat[400] = 32767 - 32768j
                raw = np.column_stack((np.rint(xfloat.real), np.rint(xfloat.imag)))
                clip_count = int(np.count_nonzero((raw < -32768) | (raw > 32767)))
                x = np.clip(raw, -32768, 32767).astype(np.int16)
                if label == "signed_endpoints":
                    x = rng.choice(np.array([-32768, 32767], np.int16), size=x.shape)
                direct, _ = direct_scores(x, h)
                floating = float_scores(x, template)
                current = fft.xfft_bitacc_match_scores(x, h, model)
                cases.append(
                    {
                        "edge": edge,
                        "control": label,
                        "cfo_hz": cfo,
                        "snr_db": snr,
                        "known_start": start,
                        "clipped_components": clip_count,
                        "input_ci16_sha256": hashlib.sha256(
                            x.astype("<i2").tobytes()
                        ).hexdigest(),
                        "score_at_known_start": None
                        if start is None
                        else {
                            "direct": int(direct[start]),
                            "float": int(floating[start]),
                            "fft": int(current.stream.scores[start]),
                        },
                        "vs_float": compare(floating, direct),
                        "vs_current_fft": compare(current.stream.scores, direct),
                    }
                )
    result = {
        "schema": SCHEMA,
        "source_pins": PINS,
        "predeclared_comparison_gates": GATES,
        "script_sha256": digest(Path(__file__)),
        "rng_seed": 0x66C0A25E,
        "cmodel_archive_sha256": digest(fft.INSTALLED_CMODEL_ARCHIVE),
        "kernels": reports,
        "frozen_reference_path": str(frozen),
        "frozen_reference_reproduced_exactly": True,
        "vs_frozen_scores": golden_comparison,
        "cases": cases,
        "schedule": [
            schedule(c, l)
            for c, l in [
                (100_000_000, 11),
                (150_000_000, 7),
                (175_000_000, 6),
                (200_000_000, 5),
                (200_000_000, 6),
            ]
        ]
        + [
            schedule(200_000_000, 6, stall_every=100, stall_length=s)
            for s in (100, 200, 400, 1000)
        ]
        + [
            schedule(200_000_000, 6, count=1_800_000, stall_every=100, stall_length=200)
        ],
        "limits": [
            "No change to production RTL or goldens",
            "No full receiver fit or live RF claim",
            "Synthetic 1536-sample controls do not qualify map cadence, 120 ms visits or 300 s scanning",
            "30/60 MS/s kernel provenance checked; end-to-end source DDC not exercised",
            "No held-out real capture or independent 2.5 MS/s GLRT evaluated",
        ],
    }
    result["summary"] = {
        "cases": len(cases),
        "float_comparison_failures": sum(
            not c["vs_float"]["comparison_pass"] for c in cases
        ),
        "fft_comparison_failures": sum(
            not c["vs_current_fft"]["comparison_pass"] for c in cases
        ),
        "max_score_delta_float": max(
            c["vs_float"]["max_abs_score_delta"] for c in cases
        ),
        "max_score_delta_fft": max(
            c["vs_current_fft"]["max_abs_score_delta"] for c in cases
        ),
    }
    (output / "numerical_schedule.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result["summary"], sort_keys=True))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen", type=Path, default=FROZEN)
    args = parser.parse_args()
    run(args.output, args.frozen)
