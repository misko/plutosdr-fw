"""Signed RTL rounding against an integer, sign-magnitude reference."""

from pathlib import Path
import random
import shutil
import subprocess

import pytest

RTL = Path(__file__).resolve().parents[2] / "hdl/library/starlink_pss_acquisition"


@pytest.fixture(scope="module")
def simulator(tmp_path_factory):
    assert shutil.which("iverilog") and shutil.which("vvp")
    directory = tmp_path_factory.mktemp("pilot-rounding")
    executable = directory / "rounding.vvp"
    subprocess.run([
        "iverilog", "-g2012", "-Wall", "-s", "tb_starlink_pilot_rounding",
        "-o", str(executable), *(str(RTL / name) for name in [
            "starlink_pilot_ddc.v", "starlink_pilot_halfband2.v",
            "starlink_pilot_fir3.v", "tb/tb_starlink_pilot_rounding.sv"]),
    ], check=True, capture_output=True, text=True, timeout=60)
    for name in ["pilot_mixer_q16.mem", "pilot_halfband2_q17.mem", "pilot_fir3_q17.mem"]:
        shutil.copyfile(RTL / name, directory / name)
    return directory, executable


def _reference(value, fraction_bits):
    # Deliberately retain the original mathematical magnitude construction;
    # do not duplicate the new signed-floor RTL implementation as its oracle.
    quotient, remainder = divmod(abs(value), 1 << fraction_bits)
    half = 1 << (fraction_bits - 1)
    quotient += remainder > half or (remainder == half and quotient % 2 == 1)
    signed = -quotient if value < 0 else quotient
    clipped = max(-32768, min(32767, signed))
    return (int(clipped != signed) << 16) | (clipped & 0xffff)


@pytest.mark.parametrize("mode,width,fraction_bits", [(0, 35, 16), (1, 39, 17), (2, 44, 17)])
def test_every_output_bucket_ties_clipping_and_full_width_extremes(
        simulator, mode, width, fraction_bits):
    directory, executable = simulator
    scale = 1 << fraction_bits
    half = scale >> 1
    # All CI16 integer buckets plus both clipping boundaries, at exact integers,
    # half +/- 1, exact halves, and the last fraction before the next integer.
    values = [integer * scale + fraction
              for integer in range(-32771, 32772)
              for fraction in (0, 1, half - 1, half, half + 1, scale - 1)]
    lo, hi = -(1 << (width - 1)), (1 << (width - 1)) - 1
    values += [lo, lo + 1, lo + half, hi - half, hi - 1, hi]
    rng = random.Random(81723 + mode)
    values += [rng.randint(lo, hi) for _ in range(10000)]
    with (directory / "rounding.txt").open("w") as stream:
        for value in values:
            stream.write(f"{mode} {value & ((1 << 44)-1):011x} "
                         f"{_reference(value, fraction_bits):05x}\n")
    result = subprocess.run(["vvp", str(executable)], cwd=directory,
                            check=True, capture_output=True, text=True, timeout=60)
    assert result.stdout.strip() == f"PILOT_ROUNDING_PASS count={len(values)}"
