"""Replay retained original native IQ, then evaluate its bounded local pilot fit."""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
import math
import re
import struct
from pathlib import Path

from tools.starlink_glrt_native_abi import NativeResult
from tools.starlink_glrt_native_replay import verify_capture


class Estimate(C.Structure):
    _fields_ = [(name, C.c_double) for name in (
        "delay_correction_s", "residual_cfo_hz", "cfo_hz", "coherence",
        "linearized_coherence")]+[("rejection", C.c_uint32)]


def evaluate_capture(capture: Path, bank: Path, solver: Path, *, solver_sha256: str) -> dict:
    """All original-IQ arithmetic must match before a local fit can be supported.

    The pinned native host library validates the GLN1 envelope directly; no
    retained packet is relabeled as a scheduled result. The same full-pilot
    Gram matrix and rejection gates apply to GLN1 and GLS1 fits.
    """
    if (re.fullmatch(r"[0-9a-f]{64}", solver_sha256) is None or
            hashlib.sha256(solver.read_bytes()).hexdigest() != solver_sha256):
        raise ValueError("native support solver library differs from its pinned digest")
    library = C.CDLL(str(solver.resolve()))
    try:
        solve = library.glrt_native_solve_capture
    except AttributeError as error:
        raise ValueError("native support library lacks the explicit GLN1 solver") from error
    solve.argtypes = [C.POINTER(C.c_uint32), C.POINTER(Estimate)]
    solve.restype = C.c_int
    summary_bytes = (capture/"summary.json").read_bytes()
    replay = verify_capture(capture, bank)
    if hashlib.sha256(summary_bytes).hexdigest() != replay["transport_summary_sha256"]:
        raise ValueError("native transport receipt changed during independent IQ replay")
    receipts = json.loads(summary_bytes)["jobs"]
    fits = []
    for index, job in enumerate(replay["jobs"]):
        payload = (capture/f"job-{index}"/"result.raw").read_bytes()
        if hashlib.sha256(payload).hexdigest() != receipts[index]["result_sha256"]:
            raise ValueError("native result changed after independent IQ replay")
        result = NativeResult.decode(payload)
        if result.start != job["start"] or result.tag != job["tag"]:
            raise ValueError("native result changed after independent IQ replay")
        estimate = Estimate()
        if solve((C.c_uint32*32)(*struct.unpack("<32I", payload)), C.byref(estimate)) != 0:
            raise ValueError("GLN1 local solver rejected its result envelope")
        values = {name: getattr(estimate, name) for name, _ in Estimate._fields_[:-1]}
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("native local solver returned a nonfinite estimate")
        supported = estimate.rejection == 0
        fits.append(dict(tag=result.tag, start_sample=str(result.start), supported=supported,
            rejection=estimate.rejection, coherence=estimate.coherence,
            linearized_coherence=estimate.linearized_coherence,
            delay_correction_s=estimate.delay_correction_s if supported else None,
            residual_cfo_hz=estimate.residual_cfo_hz if supported else None,
            cfo_hz=estimate.cfo_hz if supported else None))
    if hashlib.sha256(solver.read_bytes()).hexdigest() != solver_sha256:
        raise ValueError("native support library changed during evaluation")
    return dict(schema="starlink-gln1-native-support/v1",
        status="supported_local_fits" if all(fit["supported"] for fit in fits) else "local_fit_rejected",
        fits=fits, replay=replay, solver_sha256=solver_sha256,
        scope="full-pilot local timing/CFO fit conditional on the supplied prediction",
        acquisition_verified=False, source_continuity_verified=False, precision_qualified=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("capture", "bank", "solver", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--solver-sha256", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("native support output already exists")
    try:
        result = evaluate_capture(args.capture, args.bank, args.solver, solver_sha256=args.solver_sha256)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = dict(status="failed", error=f"{type(error).__name__}: {error}", precision_qualified=False)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write("\n")
    print(json.dumps(result, allow_nan=False))
    return int(result["status"] != "supported_local_fits")


if __name__ == "__main__":
    raise SystemExit(main())
