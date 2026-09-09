"""One reproducible engineering candidate; changes require a new profile name."""
from __future__ import annotations

CANDIDATE = "glrt-upper-candidate-v1"
FPGA_GATES = (13107, 19661, 9831)  # Q16: approximately .20 acquisition, .30 exact, .15 margin.
HOST_GATES = (.175, .025)  # Different estimator; these are not FPGA score equivalents.


def profile(gates, *, requested=None):
    gates = tuple(gates)
    if len(gates) != 3 or any(type(value) is not int or not 0 <= value <= 65536 for value in gates):
        raise ValueError("three integer Q16 gates must lie in [0, 65536]")
    if requested is not None and (requested != CANDIDATE or gates != FPGA_GATES):
        raise ValueError("named candidate profile does not allow different gates")
    return {"name": CANDIDATE if gates == FPGA_GATES else "custom-development",
            "fpga_gates_q16": list(gates), "host_gates": list(HOST_GATES),
            "status": "engineering candidate; not calibrated RF qualification"}


def add_arguments(parser, *, exact_option="--exact-q16"):
    parser.add_argument("--profile", choices=(CANDIDATE,),
                        help="require the frozen candidate gates; explicit overrides otherwise label a custom development run")
    parser.add_argument("--acquisition-q16", type=int, default=FPGA_GATES[0])
    parser.add_argument(exact_option, type=int, default=FPGA_GATES[1])
    parser.add_argument("--margin-q16", type=int, default=FPGA_GATES[2])
