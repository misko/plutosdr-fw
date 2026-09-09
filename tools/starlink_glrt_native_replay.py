"""Independent integer replay of saved GLN1 original-IQ bring-up captures."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

from tools.starlink_glrt_native_abi import SAMPLES, NativeResult

BANK_SHA256 = "b04a2fab04e89229916afedfa1b34ba327d99d50968b2a81ddb48a4f8293f5e8"
ANGLES = tuple(round(math.atan(2**-stage)*2**18/(2*math.pi)) for stage in range(16))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def round_even(value: int, denominator: int) -> int:
    floor, remainder = divmod(value, denominator)
    return floor + int(2*remainder > denominator or (2*remainder == denominator and floor & 1))


def coefficients(bank: bytes) -> list[tuple[int, int, int, int]]:
    if digest(bank) != BANK_SHA256:
        raise ValueError("native template differs from the qualified original-input bank")
    raw = []
    for text in bank.splitlines():
        word, terms = int(text, 16), []
        for bits, shift in ((12, 13), (13, 9), (14, 4), (15, 0)):
            pair = []
            for _ in range(2):
                value = word & ((1 << bits)-1)
                pair.append((value-(1 << bits) if value >> (bits-1) else value) << shift)
                word >>= bits
            terms.append(pair)
        # Closed-form polynomial; no finite-width recurrence or RTL state.
        for phase in range(24):
            raw.append(tuple(sum(math.comb(phase, order)*terms[order][axis]
                                 for order in range(4)) for axis in range(2)))
    if len(raw) != SAMPLES+48:
        raise ValueError("native bank lacks the full pilot and both guards")
    result = []
    for n in range(24, 24+SAMPLES):
        ref_i, ref_q, slope_i, slope_q = (round_even(component, 2048) for component in (
            *raw[n], 30*(raw[n+1][0]-raw[n-1][0]), 30*(raw[n+1][1]-raw[n-1][1])))
        quantized = (ref_i, ref_q, slope_i, slope_q)
        if any(component < -32768 or component > 32767 for component in quantized):
            raise ValueError("qualified native coefficient clips")
        result.append(quantized)
    return result


def rotate(i: int, q: int, phase: int) -> tuple[int, int]:
    angle = ((-phase) % 2**32) // 2**14
    x, y = 16*i, 16*q
    if ((angle >> 17) ^ (angle >> 16)) & 1:
        x, y, angle = -x, -y, angle ^ (1 << 17)
    z = angle if angle < 2**17 else angle-2**18
    for stage, step in enumerate(ANGLES):
        direction = 1 if z >= 0 else -1
        x, y, z = x-direction*(y >> stage), y+direction*(x >> stage), z-direction*step
    return round_even(x, 16), round_even(y, 16)


def verify(result: NativeResult, iq: bytes, bank: bytes) -> dict[str, object]:
    result.require_complete()
    if not result.capture_requested or len(iq) != 4*SAMPLES or result.capture_delivered != SAMPLES:
        raise ValueError("replay requires all original CI16 samples of a captured pilot")
    sums, prefix, energy = [0, 0, 0, 0], [0, 0], 0
    for n, ((i, q), (ri, rq, di, dq)) in enumerate(zip(
            struct.iter_unpack("<hh", iq), coefficients(bank), strict=True)):
        a, b = rotate(i, q, result.phase_seed+n*result.phase_step)
        # Direct four-product complex formula, independent of the FPGA's
        # three-multiplier factorization. Python integers cannot wrap.
        products = (a*ri+b*rq, b*ri-a*rq, -a*di-b*dq, a*dq-b*di)
        for k, value in enumerate(products):
            sums[k] += value
        for k in range(2):
            prefix[k] += (SAMPLES-1-n)*products[k]
        energy += a*a+b*b
    calculated = (*sums, *prefix, energy)
    reported = (*result.reference_sum, *result.delay_sum, *result.reference_prefix_integral, result.observed_energy)
    names = ("reference_i", "reference_q", "delay_i", "delay_q", "prefix_i", "prefix_q", "energy")
    differences = {name: observed-expected for name, observed, expected in zip(names, reported, calculated, strict=True)}
    if any(differences.values()):
        raise ValueError(f"native integer replay differs: {differences}")
    return {"tag": result.tag, "start": result.start, "samples": SAMPLES,
            "integer_moments": dict(zip(names, calculated, strict=True)),
            "iq_sha256": digest(iq), "bank_sha256": digest(bank),
            "exact_integer_match": True, "precision_qualified": False}


def verify_capture(capture: Path, bank: Path) -> dict[str, object]:
    protocol_bytes = (capture/"protocol.json").read_bytes()
    summary_bytes = (capture/"summary.json").read_bytes()
    protocol, summary = json.loads(protocol_bytes), json.loads(summary_bytes)
    if (protocol.get("schema") != "starlink-gln1-native-bringup/v1"
            or summary.get("status") != "transport_pass" or summary.get("failures") != []
            or type(protocol.get("jobs")) is not int or not 1 <= protocol["jobs"] <= 3
            or len(summary["jobs"]) != protocol["jobs"]):
        raise ValueError("capture lacks a complete bounded native transport receipt")
    bank_bytes = bank.read_bytes()
    jobs = []
    for index, receipt in enumerate(summary["jobs"]):
        root = capture/f"job-{index}"
        payload, iq = (root/"result.raw").read_bytes(), (root/"iq.ci16").read_bytes()
        result = NativeResult.decode(payload)
        if digest(payload) != receipt["result_sha256"] or digest(iq) != receipt["iq_sha256"]:
            raise ValueError("saved native evidence differs from its transport hashes")
        if (result.tag != protocol["tag"]+index or result.tag != receipt["tag"]
                or result.start != receipt["start"] or result.count != receipt["samples"]
                or result.phase_seed != protocol["phase_seed"] or result.phase_step != protocol["phase_step"]
                or result.sequence != 0):
            raise ValueError("native evidence differs from the requested job or transport receipt")
        jobs.append(verify(result, iq, bank_bytes))
    return {"schema": "starlink-gln1-native-replay/v1", "status": "arithmetic_pass", "jobs": jobs,
            "protocol_sha256": digest(protocol_bytes), "transport_summary_sha256": digest(summary_bytes),
            "source_sha256": {str(path.resolve()): digest(path.read_bytes()) for path in (
                Path(__file__), Path(__file__).with_name("starlink_glrt_native_abi.py"))},
            "precision_qualified": False, "hardware_identity_and_calibration_required": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("replay output already exists")
    try:
        result = verify_capture(args.capture, args.bank)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"status": "failed", "error": f"{type(error).__name__}: {error}", "precision_qualified": False}
    with args.output.open("x") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    print(json.dumps(result, indent=2))
    return int(result["status"] != "arithmetic_pass")


if __name__ == "__main__":
    raise SystemExit(main())
