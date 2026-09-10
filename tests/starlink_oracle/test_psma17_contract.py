"""Stage A only: real integer DDC/map/AXI, never a transform or RF test.

The wrapper-admission probe uses an explicitly inactive core interface stub.
The lifecycle bench instead uses real map RAM and DDC, with synthetic scores.
"""

import itertools
import os
import subprocess
from pathlib import Path

import pytest

from tests.starlink_oracle.psma17_projection import inverse_stage_a

ROOT = Path(__file__).resolve().parents[2]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", ROOT / "hdl")) / "library"
TOP = "tb_axi_starlink_pss_psma17"
SOURCES = [
    "axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v",
    "axi_starlink_pss_phase_map/starlink_pss_axi_lite.v",
    "starlink_pss_acquisition/starlink_pss_phase_map.v",
    "starlink_pss_acquisition/starlink_pss_phase_map_bank.v",
    "starlink_pss_acquisition/starlink_pss_acquisition_health.v",
    "starlink_pss_acquisition/starlink_pss_x2_ddc.v",
]


def simulate(directory, top, sources, parameters=()):
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / "test.vvp"
    command = ["iverilog", "-g2012", "-Wall", "-s", top, "-o", str(executable)]
    command += [f"-P{top}.{name}={value}" for name, value in parameters]
    command += [str(path) for path in sources]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    (directory / "compile.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    result = subprocess.run(["vvp", str(executable)], cwd=directory,
                            capture_output=True, text=True, timeout=30, check=False)
    (directory / "simulation.log").write_text(result.stdout + result.stderr)
    return result


@pytest.mark.parametrize("health,map_summary", list(itertools.product([0, 1], repeat=2)))
def test_real_ddc_psma17_lifecycle(tmp_path, health, map_summary):
    result = simulate(tmp_path, TOP, [HDL / path for path in [
        "axi_starlink_pss_acquisition/tb/tb_axi_starlink_pss_psma17.sv", *SOURCES,
    ]], [("HEALTH_COUNTERS_FROM_FLAGS", health), ("MAP_COUNTERS_FROM_FLAG", map_summary)])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PSMA17_STAGE_A_PASS") == 1
    assert result.stdout.count("PSMA17_REAL_DDC_LIFETIME_PASS") == 2
    assert result.stdout.count("PSMA17_COUNTER_INTERFACE_PASS") == 1
    assert "FAIL" not in result.stdout and "FATAL:" not in result.stdout


@pytest.mark.parametrize("name,value", [
    ("INPUT_RATE_MSPS", 15), ("INPUT_RATE_MSPS", 60), ("INPUT_RATE_MSPS", 29),
    ("ENABLE_PILOT_TAP", 0), ("ENABLE_PILOT_TAP", 2),
    ("USE_SHARED_XFFT", 0), ("USE_SHARED_XFFT", 2),
    ("USE_REALTIME_XFFT", 0), ("USE_REALTIME_XFFT", 2),
    ("ENABLE_BOUNDARY_STOP", 0), ("ENABLE_BOUNDARY_STOP", 2),
    ("USE_BANK_OWNED_XFFT", 0), ("USE_BANK_OWNED_XFFT", 2),
    ("COEFFICIENT_ENERGY", 1073742825),
])
def test_controller_rejects_incomplete_new_contract(tmp_path, name, value):
    result = simulate(tmp_path, TOP, [HDL / path for path in [
        "axi_starlink_pss_acquisition/tb/tb_axi_starlink_pss_psma17.sv", *SOURCES,
    ]], [(name, value)])
    assert result.returncode != 0 and "FATAL:" in result.stdout
    assert "PSMA17_STAGE_A_PASS" not in result.stdout


def inactive_core(tmp_path):
    # Interface-only inactive core: the original legacy stub's refusal to
    # simulate STOP is preserved in its source and all existing tests. Here
    # its nonfunctional outputs are used solely for public parameter guards.
    stub = (HDL / "axi_starlink_pss_acquisition/tb/starlink_pss_iq_to_phase_map_stub.v").read_text()
    marker = '  initial if (ENABLE_BOUNDARY_STOP) $fatal(1, "legacy acquisition stub has no stop engine");'
    assert stub.count(marker) == 1
    stub = stub.replace(marker, "  // Admission-only inactive interface, no STOP-engine claim.")
    stub_path = tmp_path / "inactive_core.v"
    stub_path.write_text(stub)
    return stub_path


def wrapper_probe(tmp_path, parameters):
    stub_path = inactive_core(tmp_path)
    choices = ", ".join(f".{name}({value})" for name, value in parameters.items())
    bench = tmp_path / "probe.sv"
    bench.write_text(f"""module probe;
      axi_starlink_pss_acquisition #({choices}) dut();
      initial begin
        #1;
        $display("WRAPPER_ADMISSION version=%h caps=%h kernel=%s energy=%0d bank=%0d rt=%0d pilot=%0d",
          dut.phase_map_control.VERSION, dut.phase_map_control.CAPABILITIES,
          dut.acquisition.KERNEL_ROM_FILE, dut.acquisition.COEFFICIENT_ENERGY,
          dut.acquisition.USE_BANK_OWNED_XFFT, dut.phase_map_control.USE_REALTIME_XFFT,
          dut.phase_map_control.ENABLE_PILOT_TAP);
        $finish;
      end
    endmodule
    """)
    return simulate(tmp_path, "probe", [bench, stub_path,
        HDL / "axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v",
        HDL / "starlink_pss_acquisition/starlink_pss_sample_cdc.v",
        *[HDL / path for path in SOURCES[:2]],
        HDL / "starlink_pss_acquisition/starlink_pss_x2_ddc.v",
    ])


def test_real_wrapper_disabled_ddc_startup_and_reset_lifetime(tmp_path):
    result = simulate(tmp_path, "tb_axi_starlink_pss_psma17_startup", [
        HDL / "axi_starlink_pss_acquisition/tb/tb_axi_starlink_pss_psma17_startup.sv",
        inactive_core(tmp_path),
        HDL / "axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v",
        HDL / "starlink_pss_acquisition/starlink_pss_sample_cdc.v",
        *[HDL / path for path in SOURCES[:2]],
        HDL / "starlink_pss_acquisition/starlink_pss_x2_ddc.v",
    ])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PSMA17_STARTUP_PASS") == 1
    assert "FAIL" not in result.stdout and "FATAL:" not in result.stdout


def test_historical_positional_controller_parameters_preserved(tmp_path):
    bench = tmp_path / "position.sv"
    bench.write_text("""module position;
      axi_starlink_pss_phase_map_sync #(20000,15,64,16,30,0,0,1,1,31'd1073744004) dut();
      initial begin #1;
        if (dut.HEALTH_COUNTERS_FROM_FLAGS != 1 || dut.MAP_COUNTERS_FROM_FLAG != 1 ||
            dut.COEFFICIENT_ENERGY != 1073744004 || dut.USE_BANK_OWNED_XFFT != 0 ||
            dut.VERSION != 32'h10002 || dut.CAPABILITIES != 32'h7f)
          $fatal(1, "old positional ABI changed");
        $display("PSMA17_POSITIONAL_LEGACY_PASS"); $finish;
      end
    endmodule
    """)
    result = simulate(tmp_path, "position", [bench, *[HDL / path for path in SOURCES[:2]]])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PSMA17_POSITIONAL_LEGACY_PASS") == 1


@pytest.mark.parametrize("rate,pilot,shared,realtime,bank,stop", [
    (30, *bits) for bits in itertools.product([0, 1], repeat=5)
] + [(rate, 1, 1, 1, 1, 1) for rate in [15, 60, 29]] + [
    (30, 1, 1, 1, 2, 1), (30, 2, 1, 1, 1, 1), (30, 1, 2, 1, 1, 1),
    (30, 1, 1, 2, 1, 1), (30, 1, 1, 1, 1, 2),
])
def test_public_wrapper_admission(tmp_path, rate, pilot, shared, realtime, bank, stop):
    parameters = dict(zip([
        "INPUT_RATE_MSPS", "ENABLE_PILOT_TAP", "USE_SHARED_XFFT",
        "USE_REALTIME_XFFT", "USE_BANK_OWNED_XFFT", "ENABLE_BOUNDARY_STOP",
    ], [rate, pilot, shared, realtime, bank, stop], strict=True))
    result = wrapper_probe(tmp_path, parameters)
    legacy = rate == 30 and bank == shared == realtime == stop == 0
    new = (rate, pilot, shared, realtime, bank, stop) == (30, 1, 1, 1, 1, 1)
    if legacy or new:
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.count("WRAPPER_ADMISSION") == 1
        assert f"version={'00010007' if new else '00010002'}" in result.stdout
        assert f"caps={'000007ff' if new else '0000007f'}" in result.stdout
        assert "kernel=upper_edge_pss30_x2_ddc_kernel_q17.mem energy=1073744004" in result.stdout
        assert f"bank={bank} rt={realtime} pilot={pilot}" in result.stdout
    else:
        assert result.returncode != 0 and "FATAL:" in result.stdout
        assert "WRAPPER_ADMISSION" not in result.stdout


@pytest.mark.parametrize("parameters,version,caps,energy", [
    ({}, "00010001", "0000003f", 1073742825),
    ({"INPUT_RATE_MSPS": 30}, "00010002", "0000007f", 1073744004),
    ({"INPUT_RATE_MSPS": 60}, "00010004", "000000ff", 1073765335),
    ({"USE_SHARED_XFFT": 1}, "00010005", "0000013f", 1073742825),
    ({"USE_SHARED_XFFT": 1, "ENABLE_BOUNDARY_STOP": 1}, "00010006", "0000033f", 1073742825),
    ({"USE_SHARED_XFFT": 1, "USE_REALTIME_XFFT": 1, "ENABLE_PILOT_TAP": 1,
      "ENABLE_BOUNDARY_STOP": 1}, "00010006", "0000033f", 1073742825),
])
def test_old_public_identities_preserved(tmp_path, parameters, version, caps, energy):
    result = wrapper_probe(tmp_path, parameters)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"version={version} caps={caps}" in result.stdout
    assert f"energy={energy} bank=0" in result.stdout


@pytest.mark.parametrize("before,after", [
    ("32'h0000_77ff", "32'h0000_57ff"),
    ("|ddc_discontinuity_count ||", "1'b0 ||"),
    ("|| USE_BANK_OWNED_XFFT) ?", "|| 1'b0) ?"),
])
def test_new_contract_mutants_fail(tmp_path, before, after):
    original = (HDL / SOURCES[0]).read_text()
    assert original.count(before) in [1, 2]
    altered = tmp_path / "mutant.v"
    altered.write_text(original.replace(before, after))
    result = simulate(tmp_path, TOP, [
        HDL / "axi_starlink_pss_acquisition/tb/tb_axi_starlink_pss_psma17.sv",
        altered, *[HDL / path for path in SOURCES[1:]],
    ])
    assert result.returncode != 0 and "PSMA_STOP_FAIL" in result.stdout
    assert "PSMA17_STAGE_A_PASS" not in result.stdout


@pytest.mark.parametrize("filename", ["axi_starlink_pss_acquisition.v", "axi_starlink_pss_phase_map_sync.v"])
def test_exact_stage_a_inverse_and_mutation_guards(filename):
    path = f"library/axi_starlink_pss_acquisition/{filename}"
    source = (HDL.parent / path).read_text()
    expected = subprocess.run([
        "git", "-C", str(HDL.parent), "show",
        f"b49553c16319f59ad8d7b44fd24c494f96eba142:{path}",
    ], check=True, capture_output=True, text=True, timeout=10).stdout
    assert inverse_stage_a(path, source) == expected
    # Changed-hunk and unchanged-body mutations must both be rejected, not
    # stripped away by a projection that weakens the previous body assertion.
    for before, after in [("USE_BANK_OWNED_XFFT = 0", "USE_BANK_OWNED_XFFT = 1"),
                          ("endmodule", "endmodule // unreviewed")]:
        assert source.count(before) == 1
        with pytest.raises(AssertionError, match="unreviewed complete"):
            inverse_stage_a(path, source.replace(before, after))


BANK_FIELDS = ["INPUT_RATE_MSPS", "ENABLE_PILOT_TAP", "USE_SHARED_XFFT",
               "USE_REALTIME_XFFT", "ENABLE_BOUNDARY_STOP", "USE_BANK_OWNED_XFFT"]


@pytest.mark.parametrize("field,literal", [
    (field, literal) for field in BANK_FIELDS for literal in ["32'hxxxxxxxx", "32'hzzzzzzzz"]
] + [("USE_BANK_OWNED_XFFT", "-1"), ("USE_BANK_OWNED_XFFT", "2")])
def test_wrapper_literal_unknown_bank_contract_rejected(tmp_path, field, literal):
    # Exact instance literals: do NOT use -P, whose unknown parsing differs.
    parameters = dict.fromkeys(BANK_FIELDS, 1)
    parameters["INPUT_RATE_MSPS"] = 30
    parameters[field] = literal
    result = wrapper_probe(tmp_path, parameters)
    assert result.returncode != 0 and "FATAL:" in result.stdout
    assert "WRAPPER_ADMISSION" not in result.stdout
    assert "bank-owned PSMA 1.7 requires" in result.stdout or \
        "USE_BANK_OWNED_XFFT must be zero or one" in result.stdout


@pytest.mark.parametrize("field,literal", [
    (field, literal) for field in [*BANK_FIELDS, "COEFFICIENT_ENERGY"]
    for literal in ["32'hxxxxxxxx", "32'hzzzzzzzz"]
] + [("USE_BANK_OWNED_XFFT", "-1"), ("USE_BANK_OWNED_XFFT", "2")])
def test_controller_literal_unknown_bank_contract_rejected(tmp_path, field, literal):
    parameters = dict.fromkeys(BANK_FIELDS, 1)
    parameters["INPUT_RATE_MSPS"] = 30
    parameters["COEFFICIENT_ENERGY"] = "31'd1073744004"
    parameters[field] = literal
    choices = ", ".join(f".{name}({value})" for name, value in parameters.items())
    bench = tmp_path / "literal.sv"
    bench.write_text(f"""module literal;
      axi_starlink_pss_phase_map_sync #({choices}) dut();
      initial begin #1; $display("UNEXPECTED_LITERAL_ADMISSION"); $finish; end
    endmodule
    """)
    result = simulate(tmp_path, "literal", [bench, *[HDL / path for path in SOURCES[:2]]])
    assert result.returncode != 0 and "FATAL:" in result.stdout
    assert "UNEXPECTED_LITERAL_ADMISSION" not in result.stdout
    assert "bank-owned PSMA 1.7 requires" in result.stdout or \
        "USE_BANK_OWNED_XFFT must be zero or one" in result.stdout
