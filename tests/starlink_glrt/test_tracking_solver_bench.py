"""The radio CPU-only benchmark consumes bounded complete multirate records."""
import json
import subprocess

import pytest

from tools.generate_glrt_tracking_gram import PROFILES

from .test_native_solver import ROOT


@pytest.fixture(scope="module")
def bench(tmp_path_factory):
    output = tmp_path_factory.mktemp("tracking-solver-bench")/"bench"
    subprocess.run(["cc","-std=c99","-O2","-Wall","-Wextra","-Werror",
        str(ROOT/"tools/glrt_native_solver.c"),str(ROOT/"tools/glrt_tracking_solver_bench.c"),
        "-lm","-o",str(output)],check=True)
    return output


def record(rate,phase):
    return " ".join(f"{value:x}" for value in
        [rate,phase,2**60+13,round(rate*.00132),0,17,*([0]*16)])+"\n"


def test_benchmark_emits_profile_identity_and_explicit_rejections(bench,tmp_path):
    data = tmp_path/"records"
    data.write_text("".join(record(rate,phase) for rate,phase in PROFILES))
    result = subprocess.run([str(bench),str(data),"17"],capture_output=True,text=True,check=True)
    output = json.loads(result.stdout)
    assert output["calls"] == 17 and output["scope"] == "multirate_solver_only_no_io_or_feedback"
    assert output["elapsed_s"] >= 0 and output["mean_us"] >= 0
    assert [(r["rate_hz"],r["reference_phase"]) for r in output["records"]] == list(PROFILES)
    assert all(r["rejection"]==4 and len(r["bank_sha256"])==64 for r in output["records"])


@pytest.mark.parametrize("mutation", ["empty","partial","trailing","too_many","bad_phase","zero_calls","many_calls"])
def test_benchmark_rejects_incomplete_or_unbounded_input(bench,tmp_path,mutation):
    data = tmp_path/"records"
    text,iterations = record(2500000,0),"1"
    if mutation=="empty": text=""
    elif mutation=="partial": text=" ".join(text.split()[:-1])
    elif mutation=="trailing": text+="unexpected"
    elif mutation=="too_many": text*=65
    elif mutation=="bad_phase": text=record(2500000,4)
    elif mutation=="zero_calls": iterations="0"
    else: iterations="1000001"
    data.write_text(text)
    result = subprocess.run([str(bench),str(data),iterations],capture_output=True,text=True,check=False)
    assert result.returncode == 2 and result.stdout == ""
