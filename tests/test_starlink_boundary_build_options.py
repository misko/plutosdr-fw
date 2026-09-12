"""Execute isolated Tcl admission; no project, image, ABI or timing qualification."""

import hashlib
import os
import subprocess
from itertools import product
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HDL = Path(os.environ.get("STARLINK_PSS_TEST_HDL", str(ROOT / "hdl")))
HELPER = HDL / "projects/pluto/starlink_pss_build_options.tcl"
KEYS = {
    "rate_msps": "STARLINK_PSS_RATE_MSPS",
    "profile": "STARLINK_PSS_PROFILE",
    "shared_xfft": "STARLINK_PSS_SHARED_XFFT",
    "realtime_xfft": "STARLINK_PSS_REALTIME_XFFT",
    "boundary_stop": "STARLINK_PSS_BOUNDARY_STOP",
}
DEFAULTS = dict(zip(KEYS, ("15", "full", "0", "0", "0"), strict=True))
SHARED = {"rate_msps": "15", "profile": "paired-pilot", "shared_xfft": "1"}


def literal(value):
    """Tcl substitution-safe UTF-8 string, including braces/brackets/newlines."""
    return f"[encoding convertfrom utf-8 [binary format H* {{{str(value).encode().hex()}}}]]"


def execute(script):
    # tclsh on stdin can print a command error and continue with exit0. Catch
    # the entire harness so fixture/source errors cannot masquerade as verdicts.
    guarded = "if {[catch {\n" + script + "\n} message]} {puts stderr $message; exit 3}\n"
    return subprocess.run(["tclsh"], input=guarded, text=True, capture_output=True,
                          check=False, timeout=10)


def resolve(fields, *, helper=HELPER, ambient=None):
    environment = {KEYS.get(key, key): value for key, value in fields.items()}
    script = f"source {literal(helper)}\n"
    for key, value in (ambient or {}).items():
        script += f"set ::env({KEYS.get(key, key)}) {literal(value)}\n"
    script += "set environment [dict create " + " ".join(
        f"{literal(key)} {literal(value)}" for key, value in environment.items()) + "]\n"
    script += ("if {[catch {pss_resolve_build_options $environment} options]} "
               "{puts stderr $options; exit 2}\n")
    script += "dict for {key value} $options {puts \"$key=$value\"}\n"
    return execute(script)


def admitted(fields, *, helper=HELPER, ambient=None):
    result = resolve(fields, helper=helper, ambient=ambient)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) == len(DEFAULTS)
    actual = dict(line.split("=", 1) for line in lines)
    expected = DEFAULTS | {key: value for key, value in fields.items() if key in KEYS}
    assert actual == expected
    return actual


def rejected(fields, *, message, helper=HELPER):
    result = resolve(fields, helper=helper)
    assert result.returncode == 2, result.stdout + result.stderr
    assert message in result.stderr
    assert not result.stdout


def test_defaults_are_explicitly_off_and_ignore_ambient_selector():
    admitted({}, ambient={key: "1" for key in KEYS})
    admitted({"unrelated": "[error SHOULD_NOT_EVALUATE]; { arbitrary }\n"})


@pytest.mark.parametrize("profile,rate", list(product(
    ("full", "detector-only", "paired-pilot", "acquisition-only"), ("15", "30", "60"))))
def test_existing_unshared_profiles_and_rates_remain_admissible(profile, rate):
    admitted({"profile": profile, "rate_msps": rate})
    admitted({"profile": profile, "rate_msps": rate, "boundary_stop": "0"})


def test_injection_keeps_its_existing_15msps_only_contract():
    admitted({"profile": "acquisition-injection"})
    admitted({"profile": "acquisition-injection", "rate_msps": "15"})
    for rate in ("30", "60"):
        rejected({"profile": "acquisition-injection", "rate_msps": rate},
                 message="acquisition-injection")


def test_coarse25_is_explicit_bypass_only_without_old_fft_features():
    admitted({"profile": "coarse25", "rate_msps": "2.5"})
    for rate in ("15", "30", "60"):
        rejected({"profile": "coarse25", "rate_msps": rate}, message="coarse25 requires explicit")
    rejected({"profile": "coarse25"}, message="coarse25 requires explicit")
    for profile in ("full", "paired-pilot", "detector-only", "acquisition-only"):
        rejected({"profile": profile, "rate_msps": "2.5"}, message="coarse25 requires explicit")
    for feature in ("shared_xfft", "realtime_xfft", "boundary_stop"):
        rejected({"profile": "coarse25", "rate_msps": "2.5", feature: "1"}, message="requires explicit")


@pytest.mark.parametrize("realtime,boundary", list(product((None, "0", "1"), repeat=2)))
def test_stop_never_implies_realtime_and_shared_nonrealtime_is_preserved(realtime, boundary):
    fields = SHARED.copy()
    if realtime is not None:
        fields["realtime_xfft"] = realtime
    if boundary is not None:
        fields["boundary_stop"] = boundary
    admitted(fields)


@pytest.mark.parametrize("field", ("shared_xfft", "realtime_xfft", "boundary_stop"))
@pytest.mark.parametrize("value", ("", "true", "false", "yes", "01", "1.0", " 1", "1 ",
                                   "1\n", "-1", "2", "[error injected]", "1; exit 0"))
def test_bool_selectors_are_literal_not_tcl_boolean_or_injectable(field, value):
    rejected(SHARED | {field: value}, message=KEYS[field])


@pytest.mark.parametrize("rate", ("", "015", "15.0", "25", "120", " 15", "15 ", "[expr 15]"))
def test_rate_is_a_literal_supported_enum(rate):
    rejected({"rate_msps": rate}, message=KEYS["rate_msps"])


@pytest.mark.parametrize("profile", ("", "paired", "PAIRED-PILOT", "paired-pilot ", "[error x]"))
def test_profile_is_a_literal_supported_enum(profile):
    rejected({"profile": profile}, message=KEYS["profile"])


@pytest.mark.parametrize("boundary,realtime", list(product(("0", "1"), repeat=2)))
@pytest.mark.parametrize("missing", ("rate_msps", "profile"))
def test_shared_mode_requires_explicit_rate_and_profile(boundary, realtime, missing):
    fields = SHARED | {"boundary_stop": boundary, "realtime_xfft": realtime}
    del fields[missing]
    rejected(fields, message="shared-XFFT requires explicit")


@pytest.mark.parametrize("boundary,realtime", list(product(("0", "1"), repeat=2)))
@pytest.mark.parametrize("change", ({"rate_msps": "30"}, {"rate_msps": "60"},
                                    {"profile": "full"}, {"profile": "detector-only"},
                                    {"profile": "acquisition-only"},
                                    {"profile": "acquisition-injection"}))
def test_shared_mode_rejects_unsupported_combinations(boundary, realtime, change):
    rejected(SHARED | {"boundary_stop": boundary, "realtime_xfft": realtime} | change,
             message="shared-XFFT requires explicit")


@pytest.mark.parametrize("feature", ("realtime_xfft", "boundary_stop"))
@pytest.mark.parametrize("shared", (None, "0"))
def test_each_experimental_feature_requires_explicit_shared(feature, shared):
    fields = {"rate_msps": "15", "profile": "paired-pilot", feature: "1"}
    if shared is not None:
        fields["shared_xfft"] = shared
    rejected(fields, message="requires explicit shared")


def test_helper_rejects_non_dictionary_input():
    result = execute(f"source {literal(HELPER)}\n"
                     "if {[catch {pss_resolve_build_options {odd}} message]} "
                     "{puts stderr $message; exit 2}\n")
    assert result.returncode == 2
    assert "environment dictionary" in result.stderr


def test_source_and_calls_do_not_mutate_environment_project_or_files(tmp_path):
    # These Vivado APIs are traps, not a simulated successful project build.
    script = """
foreach command {create_project set_property ad_ip_parameter adi_project_create
                 adi_project_run create_ip launch_runs open_checkpoint} {
  proc $command {args} {error "FORBIDDEN_BUILD_SIDE_EFFECT"}
}
set before_env [lsort -stride 2 -index 0 [array get ::env]]
"""
    script += f"cd {literal(tmp_path)}\nset test_pwd [pwd]\nsource {literal(HELPER)}\n"
    script += """
set supplied {STARLINK_PSS_RATE_MSPS 15 STARLINK_PSS_PROFILE paired-pilot
              STARLINK_PSS_SHARED_XFFT 1 STARLINK_PSS_BOUNDARY_STOP 1}
set before_supplied $supplied
set first [pss_resolve_build_options $supplied]
set second [pss_resolve_build_options $supplied]
if {$first ne $second || $supplied ne $before_supplied ||
    [lsort -stride 2 -index 0 [array get ::env]] ne $before_env || [pwd] ne $test_pwd ||
    [llength [glob -nocomplain * .*]] > 2} {
  puts stderr "SIDE_EFFECT_OR_NONDETERMINISM"; exit 2
}
puts PURE_OPTIONS_PASS
"""
    result = execute(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PURE_OPTIONS_PASS"
    assert not list(tmp_path.iterdir())


def test_harness_does_not_treat_tcl_stdin_error_then_success_as_a_pass():
    result = execute('error "HARNESS_FAILURE"\nputs FALSE_PASS\n')
    assert result.returncode == 3
    assert result.stderr.strip() == "HARNESS_FAILURE"
    assert not result.stdout


# Mutants are written ONLY in pytest's temporary directory. Each violates an
# externally exercised admission rule; no production/default helper is edited.
MUTANTS = [
    ("default_on", "STARLINK_PSS_BOUNDARY_STOP boundary_stop 0",
     "STARLINK_PSS_BOUNDARY_STOP boundary_stop 1", {}, True),
    ("boolean_alias", "if {$value ni {0 1}}", "if {0}",
     SHARED | {"boundary_stop": "true"}, False),
    ("unsupported_rate", "if {$rate ni {2.5 15 30 60}}", "if {0}",
     {"rate_msps": "25"}, False),
    ("unsupported_profile", "if {$profile ni {full detector-only paired-pilot acquisition-only acquisition-injection coarse25}}",
     "if {0}", {"profile": "unknown"}, False),
    ("injection_rate", 'if {$profile eq "acquisition-injection" && $rate ne "15"}',
     "if {0}", {"profile": "acquisition-injection", "rate_msps": "30"}, False),
    ("implicit_shared_rate", "![dict exists $environment STARLINK_PSS_RATE_MSPS] || ",
     "", {"profile": "paired-pilot", "shared_xfft": "1", "boundary_stop": "1"}, False),
    ("shared_wrong_rate", '$rate ne "15" ||', '0 ||',
     SHARED | {"rate_msps": "30", "boundary_stop": "1"}, False),
    ("shared_wrong_profile", '$profile ne "paired-pilot"', "0",
     SHARED | {"profile": "full", "boundary_stop": "1"}, False),
    ("realtime_unshared", 'if {$realtime eq "1" && $shared ne "1"}', "if {0}",
     {"realtime_xfft": "1"}, False),
    ("boundary_unshared", 'if {$boundary eq "1" && $shared ne "1"}', "if {0}",
     {"boundary_stop": "1"}, False),
]


@pytest.mark.parametrize("name,before,after,fields,should_admit", MUTANTS,
                         ids=[entry[0] for entry in MUTANTS])
def test_admission_regression_detects_policy_mutations(
        tmp_path, name, before, after, fields, should_admit):
    source = HELPER.read_text()
    original_hash = hashlib.sha256(HELPER.read_bytes()).hexdigest()
    assert source.count(before) == 1, name
    mutant = tmp_path / f"{name}.tcl"
    mutant.write_text(source.replace(before, after, 1))
    original = resolve(fields)
    changed = resolve(fields, helper=mutant)
    assert (original.returncode == 0) is should_admit
    assert changed.returncode in (0, 2), changed.stderr
    assert (changed.returncode == 0) is not should_admit, changed.stdout + changed.stderr
    assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == original_hash


def entrypoint_probe(entrypoint, fields, *, readback="normal", through_tracker=False,
                     tracker_readback="normal"):
    """Execute actual entrypoint Tcl with only its external Vivado APIs modeled.

    Project probes stop at project creation. BD probes stop AFTER parameter
    readback, at the first FFT clock connection. Neither claims a Vivado build.
    """
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("STARLINK_PSS_")}
    environment.update({KEYS.get(key, key): value for key, value in fields.items()})
    path = HELPER.parent / entrypoint
    script = f"set helper {literal(HELPER)}\nset entrypoint {literal(path)}\n"
    script += f"set readback {literal(readback)}\n"
    script += f"set through_tracker {int(through_tracker)}\n"
    script += f"set tracker_readback {literal(tracker_readback)}\n"
    script += r'''
set mutations 0
set parameters [dict create]
rename source native_source
proc source {path} {
  if {$path eq $::helper || $path eq $::entrypoint} {
    return [uplevel 1 [list native_source $path]]
  }
  if {[file tail $path] eq "adi_env.tcl"} {set ::ad_hdl_dir /mock_adi; return}
  if {[file tail $path] in {adi_project_xilinx.tcl adi_board.tcl}} {return}
  error "unexpected source $path"
}
proc adi_project_create {args} {incr ::mutations; error PROJECT_CREATE_REACHED}
proc ad_ip_instance {args} {incr ::mutations}
proc ad_ip_parameter {cell property value} {
  incr ::mutations
  dict set ::parameters $cell $property $value
}
proc get_property {property object} {
  if {$property eq "IP_REPO_PATHS"} {return {}}
  if {$property eq "CONFIG.USE_DSP_REDUCER"} {
    puts "TRACKER_READBACK_REACHED [dict get $::parameters $object $property]"
    if {$::tracker_readback eq "normal"} {return [dict get $::parameters $object $property]}
    return $::tracker_readback
  }
  if {$property eq "CONFIG.ENABLE_BOUNDARY_STOP"} {
    puts "READBACK_REACHED [dict get $::parameters $object $property]"
    if {$::readback eq "normal"} {return [dict get $::parameters $object $property]}
    return $::readback
  }
  error "unexpected property $property"
}
proc get_bd_cells {name} {return $name}
proc ad_connect {args} {
  incr ::mutations
  if {!$::through_tracker && $args eq "sys_200m_clk starlink_pss_acquisition/fft_clk"} {
    puts "FEATURES [dict get $::parameters starlink_pss_acquisition]"
    error BD_READBACK_VERIFIED
  }
  if {$::through_tracker && $args eq "rx_clk_in axi_ad9361/rx_clk_in"} {
    puts "TRACKER_FEATURES [dict get $::parameters starlink_pss_tracker]"
    error TRACKER_READBACK_VERIFIED
  }
}
proc unknown {command args} {
  if {$command in {current_fileset set_property update_ip_catalog create_bd_intf_port
                  create_bd_port ad_ip_instance ad_ip_parameter ad_connect
                  ad_cpu_interconnect ad_cpu_interrupt ad_mem_hp0_interconnect}} {
    incr ::mutations
    return {}
  }
  error "unmodeled Vivado API $command"
}
set status [catch {source $entrypoint} message]
puts "STATUS $status MESSAGE $message MUTATIONS $mutations"
'''
    result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                            env=environment, timeout=10, check=False)
    assert result.returncode == 0 and not result.stderr, result.stdout + result.stderr
    assert "STATUS " in result.stdout
    return result.stdout


@pytest.mark.parametrize("entrypoint", ["system_project.tcl", "system_bd.tcl"])
@pytest.mark.parametrize("fields", [
    {"boundary_stop": "1"}, SHARED | {"boundary_stop": "true"},
    SHARED | {"boundary_stop": "1", "rate_msps": "30"},
    {"profile": "paired-pilot", "shared_xfft": "1", "boundary_stop": "1"},
    {"realtime_xfft": "1"}, {"rate_msps": "25"},
])
def test_real_entrypoints_reject_invalid_options_before_mutations(entrypoint, fields):
    result = entrypoint_probe(entrypoint, fields)
    assert "MUTATIONS 0" in result and "STATUS 1 MESSAGE" in result, result
    assert "PROJECT_CREATE_REACHED" not in result and "READBACK_REACHED" not in result


@pytest.mark.parametrize("fields", [{}, {"profile": "detector-only", "rate_msps": "60"},
                                    SHARED, SHARED | {"boundary_stop": "1"},
                                    SHARED | {"boundary_stop": "1", "realtime_xfft": "1"}])
def test_project_admits_legacy_and_explicit_enabled_profiles(fields):
    assert "MESSAGE PROJECT_CREATE_REACHED MUTATIONS 1" in entrypoint_probe(
        "system_project.tcl", fields)


@pytest.mark.parametrize("realtime,boundary", list(product(("0", "1"), repeat=2)))
def test_bd_sets_and_reads_back_actual_stop_parameter_without_implying_realtime(realtime, boundary):
    result = entrypoint_probe("system_bd.tcl", SHARED | {
        "realtime_xfft": realtime, "boundary_stop": boundary})
    assert f"READBACK_REACHED {boundary}" in result, result
    assert f"CONFIG.USE_REALTIME_XFFT {realtime}" in result, result
    assert f"CONFIG.ENABLE_BOUNDARY_STOP {boundary}" in result, result
    assert "MESSAGE BD_READBACK_VERIFIED" in result, result


@pytest.mark.parametrize("readback", ["0", "", "unknown"])
def test_bd_rejects_missing_or_ignored_stop_parameter(readback):
    result = entrypoint_probe("system_bd.tcl", SHARED | {"boundary_stop": "1"},
                              readback=readback)
    assert "boundary-stop IP readback mismatch" in result, result
    assert "BD_READBACK_VERIFIED" not in result


@pytest.mark.parametrize("profile,rate", list(product(
    ("full", "detector-only", "paired-pilot"), ("15", "30", "60"))))
def test_unshared_tracker_keeps_existing_reducer_choice(profile, rate):
    result = entrypoint_probe("system_bd.tcl", {"profile": profile, "rate_msps": rate},
                              through_tracker=True)
    assert "MESSAGE TRACKER_READBACK_VERIFIED" in result, result
    assert f"CONFIG.USE_DSP_REDUCER {int(rate == '60')}" in result


def test_shared_paired_tracker_explicitly_selects_dsp_and_reads_it_back():
    result = entrypoint_probe("system_bd.tcl", SHARED, through_tracker=True)
    assert "MESSAGE TRACKER_READBACK_VERIFIED" in result, result
    assert "CONFIG.USE_DSP_REDUCER 1" in result


@pytest.mark.parametrize("readback", ["0", "", "unknown"])
def test_shared_tracker_rejects_ignored_or_missing_reducer_choice(readback):
    result = entrypoint_probe("system_bd.tcl", SHARED, through_tracker=True,
                              tracker_readback=readback)
    assert "tracker reducer IP readback mismatch" in result, result
    assert "TRACKER_READBACK_VERIFIED" not in result


def test_make_exports_default_off_and_tracks_helper_dependency():
    source = (HELPER.parent / "Makefile").read_text()
    assert "STARLINK_PSS_BOUNDARY_STOP ?= 0" in source
    assert "export STARLINK_PSS_BOUNDARY_STOP" in source
    assert "M_DEPS += starlink_pss_build_options.tcl" in source
