"""Offline initial-admission/public-contract checks, never live profile switching."""

import hashlib
import itertools
import subprocess

import pytest

from tests.starlink_oracle.psma17_projection import inverse_stage_a
from tests.starlink_oracle.psma18_contract import (
    BANK_FIELDS,
    CONTROLLER,
    COUNTER_STAGE_STUB,
    LIB,
    PARAMETERS,
    WRAPPER,
    lifecycle_source,
    replace_exact,
)
from tests.starlink_oracle.psma18_projection import inverse_stage_a60
from tests.starlink_oracle.test_psma17_contract import SOURCES, inactive_core, simulate


def probe(directory, parameters, wrapper=True, altered=None, check_identity=True):
    directory.mkdir(parents=True, exist_ok=True)
    choices = ", ".join(f".{name}({value})" for name, value in parameters.items())
    module = "axi_starlink_pss_acquisition" if wrapper else "axi_starlink_pss_phase_map_sync"
    prefix = "dut.phase_map_control" if wrapper else "dut"
    extra = """
        if(dut.acquisition.COEFFICIENT_ENERGY !== 1073765335 ||
           dut.acquisition.KERNEL_ROM_FILE != "upper_edge_pss60_x4_ddc_kernel_q17.mem")
          $fatal(1,"PSMA18_IDENTITY_FAIL kernel/energy");
    """ if wrapper else ""
    bench = directory / "probe.sv"
    bench.write_text(f"""module probe;
      {module} #({choices}) dut();
      initial begin #1;
        if ({int(check_identity)}) begin
        if({prefix}.VERSION !== 32'h10008 || {prefix}.CAPABILITIES !== 32'h7ff ||
           {prefix}.DDC_CONFIG !== 32'h020f0403 || {prefix}.DDC_GROUP_DELAY !== 21 ||
           {prefix}.DDC_CONTRACT !== 256'h8e807d15d5372b0a9669d1190d899697e7c2911a73ddfb23095806c2a31de5b2 ||
           {prefix}.COEFFICIENT_ENERGY !== 1073765335 || {prefix}.ENABLE_BANK60_PAIRED !== 1)
          $fatal(1,"PSMA18_IDENTITY_FAIL explicit contract");
        {extra}
        end
        $display("PSMA18_INITIAL_ADMISSION_PASS wrapper={int(wrapper)} rate=60 abi=00010008 caps=000007ff");
        $finish;
      end
    endmodule
    """)
    sources = [LIB / name for name in SOURCES[:2]]
    if wrapper:
        sources += [inactive_core(directory), LIB.parent / WRAPPER,
                    LIB / "starlink_pss_acquisition/starlink_pss_sample_cdc.v",
                    LIB / "starlink_pss_acquisition/starlink_pss_x2_ddc.v"]
    if altered:
        path, source = altered
        mutant = directory / "mutant.v"
        mutant.write_text(source)
        sources = [mutant if p == LIB.parent / path else p for p in sources]
    return simulate(directory, "probe", [bench, *sources])


def rejected(result):
    assert result.returncode != 0 and "FATAL:" in result.stdout
    assert "PSMA18_INITIAL_ADMISSION_PASS" not in result.stdout


def contract_parameters(wrapper):
    return PARAMETERS.copy() if wrapper else PARAMETERS | {"COEFFICIENT_ENERGY": "31'd1073765335"}


@pytest.mark.parametrize("wrapper", [False, True])
def test_exact_public60_initial_admission(tmp_path, wrapper):
    result = probe(tmp_path, contract_parameters(wrapper), wrapper)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PSMA18_INITIAL_ADMISSION_PASS") == 1


BAD_FIELDS = [(field, value) for field in BANK_FIELDS for value in ["32'hxxxxxxxx", "32'hzzzzzzzz"]]
BAD_FIELDS += [(field, value) for field in BANK_FIELDS if field != "INPUT_RATE_MSPS" for value in [-1, 2]]
BAD_FIELDS += [("INPUT_RATE_MSPS", value) for value in [0, 15, 30, 59, 61, -1]]
BAD_FIELDS += [(field, 0) for field in BANK_FIELDS]


@pytest.mark.parametrize("wrapper", [False, True])
@pytest.mark.parametrize("field,value", BAD_FIELDS)
def test_literal_bad_combinations_fail_closed(tmp_path, wrapper, field, value):
    # X/Z are actual SV instance literals, not Icarus -P parsing.
    parameters = contract_parameters(wrapper) | {field: value}
    rejected(probe(tmp_path, parameters, wrapper))


@pytest.mark.parametrize("value", [0, 1073742825, 1073744004, 1073765334, 1073765336,
                                   "31'hxxxxxxxx", "31'hzzzzzzzz"])
def test_controller_exact_conditioned_energy(tmp_path, value):
    rejected(probe(tmp_path, contract_parameters(False) | {"COEFFICIENT_ENERGY": value}, False))


@pytest.mark.parametrize("field", ["INPUT_RATE_MSPS", "ENABLE_PILOT_TAP", "USE_SHARED_XFFT",
                                   "USE_REALTIME_XFFT", "ENABLE_BOUNDARY_STOP", "COEFFICIENT_ENERGY"])
@pytest.mark.parametrize("literal", ["32'hxxxxxxxx", "32'hzzzzzzzz"])
def test_unknown_guard_weakening_is_behaviorally_detected(tmp_path, field, literal):
    # No identity read/check can mask this result: the admitted specimen only
    # prints a marker. Dropping case inequality must make the negative gate
    # FAIL, even though the remaining historical guards are still present.
    source = (LIB.parent / CONTROLLER).read_text()
    first, rest = source.split('      $fatal(1, "bank-owned PSMA 1.8', 1)
    first = replace_exact(first, f"{field} !==", f"{field} !=")
    mutant = first + '      $fatal(1, "bank-owned PSMA 1.8' + rest
    parameters = contract_parameters(False) | {field: literal}
    rejected(probe(tmp_path / "healthy_guard", parameters, False, check_identity=False))
    result = probe(tmp_path / "weakened_guard", parameters, False,
                   (CONTROLLER, mutant), check_identity=False)
    assert result.returncode == 0 and "PSMA18_INITIAL_ADMISSION_PASS" in result.stdout
    with pytest.raises(AssertionError):
        rejected(result)


def test_deleted_new_guard_is_behaviorally_detected(tmp_path):
    source = replace_exact((LIB.parent / CONTROLLER).read_text(),
                           "if (ENABLE_BANK60_PAIRED === 1 &&", "if (1'b0 &&")
    parameters = contract_parameters(False) | {"ENABLE_PILOT_TAP": 0}
    rejected(probe(tmp_path / "healthy_guard", parameters, False, check_identity=False))
    result = probe(tmp_path / "deleted_guard", parameters, False,
                   (CONTROLLER, source), check_identity=False)
    assert result.returncode == 0 and "PSMA18_INITIAL_ADMISSION_PASS" in result.stdout
    with pytest.raises(AssertionError):
        rejected(result)


def test_conditioned_wrapper_energy_mutation_fails_initial_admission(tmp_path):
    source = replace_exact((LIB.parent / WRAPPER).read_text(),
                           "? 31'd1073765335 :", "? 31'd1073744004 :")
    rejected(probe(tmp_path, PARAMETERS, True, (WRAPPER, source), check_identity=False))


def test_historical_stage17_positional_parameters_preserved(tmp_path):
    bench = tmp_path / "positions.sv"
    bench.write_text('''module positions;
      axi_starlink_pss_acquisition #(7,30,1,1,1,1,1) shell();
      axi_starlink_pss_phase_map_sync #(20000,15,64,16,30,1,1,1,1,31'd1073744004,1,1,1) control();
      initial begin #1;
        if(shell.ENABLE_BANK60_PAIRED !== 0 || control.ENABLE_BANK60_PAIRED !== 0 ||
           shell.phase_map_control.VERSION !== 32'h10007 || control.VERSION !== 32'h10007 ||
           shell.phase_map_control.CAPABILITIES !== 32'h7ff || control.CAPABILITIES !== 32'h7ff)
          $fatal(1,"PSMA18_POSITIONAL_FAIL");
        $display("PSMA18_POSITIONAL_LEGACY_PASS"); $finish;
      end
    endmodule
    ''')
    result = simulate(tmp_path, "positions", [bench, inactive_core(tmp_path), LIB.parent / WRAPPER,
        LIB / "starlink_pss_acquisition/starlink_pss_sample_cdc.v",
        *[LIB / name for name in SOURCES[:2]], LIB / "starlink_pss_acquisition/starlink_pss_x2_ddc.v"])
    assert result.returncode == 0 and "PSMA18_POSITIONAL_LEGACY_PASS" in result.stdout


@pytest.mark.parametrize("bits", list(itertools.product([0, 1], repeat=5)))
def test_no_partial_public60_bank_composition(tmp_path, bits):
    fields = ["USE_BANK_OWNED_XFFT", "ENABLE_PILOT_TAP", "USE_SHARED_XFFT",
              "USE_REALTIME_XFFT", "ENABLE_BOUNDARY_STOP"]
    result = probe(tmp_path, PARAMETERS | dict(zip(fields, bits, strict=True)))
    if all(bits):
        assert result.returncode == 0 and "PSMA18_INITIAL_ADMISSION_PASS" in result.stdout
    else:
        rejected(result)


@pytest.mark.parametrize("health,map_summary", list(itertools.product([0, 1], repeat=2)))
def test_public60_real_map_and_integer_fault_lifecycle(tmp_path, health, map_summary):
    bench = tmp_path / "psma18_lifecycle.sv"
    bench.write_text(lifecycle_source())
    result = simulate(tmp_path, "tb_axi_starlink_pss_psma18", [bench, *[LIB / name for name in SOURCES]],
                      [("HEALTH_COUNTERS_FROM_FLAGS", health), ("MAP_COUNTERS_FROM_FLAG", map_summary)])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PSMA18_STAGE_A_PASS") == 1
    assert result.stdout.count("PSMA18_REAL_DDC_LIFETIME_PASS") == 2
    assert result.stdout.count("PSMA18_COUNTER_INTERFACE_PASS") == 1
    assert "single_real_x2_public_fault_producer=1" in result.stdout


def counter_run(directory, mode, specimen, altered=None):
    directory.mkdir(parents=True, exist_ok=True)
    stage = LIB / "starlink_pss_acquisition/starlink_pss_x2_ddc.v"
    if specimen:
        stage = directory / "stage_output_specimen.v"
        stage.write_text(COUNTER_STAGE_STUB)
    wrapper = LIB.parent / WRAPPER
    if altered is not None:
        wrapper = directory / "wrapper_mutant.v"
        wrapper.write_text(altered)
    return simulate(directory, "tb_axi_starlink_pss_psma18_counters", [
        LIB / "axi_starlink_pss_acquisition/tb/tb_axi_starlink_pss_psma18_counters.sv",
        inactive_core(directory), wrapper,
        LIB / "starlink_pss_acquisition/starlink_pss_sample_cdc.v",
        *[LIB / name for name in SOURCES[:2]], stage,
    ], [("NEW_MODE", mode), ("COUNTER_STAGE_SPECIMEN", specimen)])


@pytest.mark.parametrize("mode,specimen", list(itertools.product([0, 1], repeat=2)))
def test_actual_wrapper_cascade_or_declared_output_specimens(tmp_path, mode, specimen):
    result = counter_run(tmp_path, mode, specimen)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("PSMA18_COUNTERS_PASS") == 1
    if specimen:
        assert result.stdout.count("PSMA18_STAGE_OUTPUT_SPECIMEN ") == 9
        assert result.stdout.count("PSMA18_COUNTER_SPECIMENS_PASS") == 1
    else:
        assert result.stdout.count("PSMA18_REAL_FIRST_ONLY_PASS") == 1
        assert result.stdout.count("PSMA18_REAL_CASCADE_PASS") == 1


@pytest.mark.parametrize("before,after,mode,specimen", [
    ("discontinuity_sum[32] ? 32'hffff_ffff : discontinuity_sum[31:0]", "discontinuity_sum[31:0]", 1, 1),
    ("{1'b0, stage_60_discontinuity_count} +", "33'd0 +", 1, 0),
    ("{1'b0, stage_30_discontinuity_count};", "33'd0;", 1, 0),
    ("ddc_discontinuity_count = ENABLE_BANK60_PAIRED ?", "ddc_discontinuity_count = 1'b1 ?", 0, 0),
    ("ddc_discontinuity_count = ENABLE_BANK60_PAIRED ?", "ddc_discontinuity_count = 1'b0 ?", 1, 0),
])
def test_counter_sum_mutations_are_killed(tmp_path, before, after, mode, specimen):
    source = replace_exact((LIB.parent / WRAPPER).read_text(), before, after)
    result = counter_run(tmp_path, mode, specimen, source)
    assert result.returncode != 0 and "PSMA18_COUNTERS_FAIL" in result.stdout
    assert "PSMA18_COUNTERS_PASS" not in result.stdout


@pytest.mark.parametrize("before,after", [
    ("32'h0001_0008", "32'h0001_0007"),
    ("32'h0000_07ff", "32'h0000_03ff"),
    ("32'h020f_0403", "32'h000f_0203"),
    ("32'd21", "32'd7"),
    ("8e807d15d5372b0a9669d1190d899697e7c2911a73ddfb23095806c2a31de5b2",
     "731426047077b036f9213db3574e4a556fd424b97a293843bd6ee085c2bf33af"),
])
def test_wrong_public_identity_mutations_are_killed(tmp_path, before, after):
    source = replace_exact((LIB.parent / CONTROLLER).read_text(), before, after)
    result = probe(tmp_path, contract_parameters(False), False, (CONTROLLER, source))
    rejected(result)
    assert "PSMA18_IDENTITY_FAIL" in result.stdout


@pytest.mark.parametrize("path", [WRAPPER, CONTROLLER])
def test_complete_legacy_body_inverse_and_strict_mutants(path):
    source = (LIB.parent / path).read_text()
    old = subprocess.run(["git", "-C", str(LIB.parent), "show",
                          f"706ffb7b5b842409d8a8714c056203d8b5555034:{path}"],
                         check=True, capture_output=True, text=True).stdout
    assert inverse_stage_a60(path, source) == old
    original = subprocess.run(["git", "-C", str(LIB.parent), "show",
                               f"b49553c16319f59ad8d7b44fd24c494f96eba142:{path}"],
                              check=True, capture_output=True, text=True).stdout
    assert inverse_stage_a(path, source) == original
    # Delete new admission, weaken X/Z comparisons, change defaults/identity,
    # or alter unrelated runtime: every complete-source mutation must reject.
    for before, after in [
        ("if (ENABLE_BANK60_PAIRED === 1 &&", "if (1'b0 &&"),
        ("INPUT_RATE_MSPS !== 60", "INPUT_RATE_MSPS != 60"),
        ("ENABLE_BANK60_PAIRED = 0", "ENABLE_BANK60_PAIRED = 1"),
        ("endmodule", "endmodule // unreviewed"),
    ]:
        mutated = replace_exact(source, before, after)
        with pytest.raises(AssertionError, match="unreviewed complete"):
            inverse_stage_a60(path, mutated)


def test_legacy_projection_adapter_has_an_exact_inverse():
    path = LIB.parent.parent / "tests/starlink_oracle/psma17_projection.py"
    text = path.read_text()
    addition = '''    if digest not in (entry["before_sha256"], entry["after_sha256"]):
        from .psma18_projection import inverse_stage_a60
        source = inverse_stage_a60(path, source)
        digest = hashlib.sha256(source.encode()).hexdigest()
'''
    original = replace_exact(text, addition, "")
    assert hashlib.sha256(original.encode()).hexdigest() == \
        "8903731793538f20a8769ae66299882c870062c57bf22d767f99d8d9daed25df"
