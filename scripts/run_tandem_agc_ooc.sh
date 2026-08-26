#!/bin/bash
# Reproducible routed out-of-context gate for the complete tandem AGC block.

set -euo pipefail
PATH=/usr/bin:/bin
export PATH

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANONICAL_SETTINGS=/opt/Xilinx/Vivado/2022.2/settings64.sh
CANONICAL_VIVADO=/opt/Xilinx/Vivado/2022.2/bin/vivado
CANONICAL_SETUP_ENV=/opt/Xilinx/Vivado/2022.2/bin/setupEnv.sh
CANONICAL_VIVADO_BINARY=/opt/Xilinx/Vivado/2022.2/bin/unwrapped/lnx64.o/vivado
CANONICAL_LIBTINFO=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE/libtinfo.so.5
CANONICAL_PYTHON=/usr/bin/python3
EXPECTED_SETTINGS_SHA256=9bf3eb45ee64972189ceb1b604d7400c086882e12f5788b3a5fefe4c7269602d
EXPECTED_VIVADO_SHA256=2924389be0c4297f3e2c4d267e22904a89962575497d0f5fd7eb15dc959e5505
EXPECTED_SETUP_ENV_SHA256=07553d9d7fb5915d44e9ac29a9c8bd33321b233231a66b5daff10985aa672d38
EXPECTED_VIVADO_BINARY_SHA256=869fa7c4f4f7256ed386c79db0e479b18d3feb201eb77e1739dba633be6446de
EXPECTED_LIBTINFO_SHA256=78a3f1dbaf81f27ba85ee0f0eb0d1176d5664446f42755c1a93d4b510f95fa7f
VIVADO_SETTINGS="${VIVADO_SETTINGS:-$CANONICAL_SETTINGS}"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

sha256() {
    sha256sum -- "$1" | awk '{print $1}'
}

[[ $# -eq 1 ]] || fail "usage: $0 <fresh-output-directory>"
[[ -r "$VIVADO_SETTINGS" ]] || fail "Vivado settings are not readable: $VIVADO_SETTINGS"
[[ "$(realpath -- "$VIVADO_SETTINGS")" == "$CANONICAL_SETTINGS" ]] ||
    fail "Vivado settings must resolve to $CANONICAL_SETTINGS"
[[ "$(sha256 "$CANONICAL_SETTINGS")" == "$EXPECTED_SETTINGS_SHA256" ]] ||
    fail "Vivado settings hash does not match the qualified installation"
[[ "$(sha256 "$CANONICAL_SETUP_ENV")" == "$EXPECTED_SETUP_ENV_SHA256" ]] ||
    fail "Vivado setupEnv hash does not match the qualified installation"
[[ "$(sha256 "$CANONICAL_VIVADO_BINARY")" == \
    "$EXPECTED_VIVADO_BINARY_SHA256" ]] ||
    fail "Vivado executable binary hash does not match the qualified installation"
[[ -r "$CANONICAL_LIBTINFO" ]] || fail "bundled libtinfo.so.5 is missing"
[[ "$(sha256 "$CANONICAL_LIBTINFO")" == "$EXPECTED_LIBTINFO_SHA256" ]] ||
    fail "bundled libtinfo.so.5 hash does not match the qualified installation"

requested_output=$1
[[ ! -e "$requested_output" && ! -L "$requested_output" ]] ||
    fail "output path must be absent: $requested_output"
output_parent="$(dirname "$requested_output")"
[[ -d "$output_parent" && ! -L "$output_parent" ]] ||
    fail "output parent must be an existing non-symlink directory: $output_parent"
output_parent="$(realpath -- "$output_parent")"
output_dir="${output_parent}/$(basename "$requested_output")"
case "$output_dir" in
    "$ROOT" | "$ROOT"/*) fail "output path must be outside the firmware tree" ;;
esac

commit="$(git -C "$ROOT" rev-parse --verify HEAD)"
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || fail "cannot resolve an exact source commit"
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] ||
    fail "firmware source tree must be clean"

umask 077
parent_identity="$(stat -c '%d:%i:%f:%u:%g' "$output_parent")"
mkdir --mode=700 -- "$output_dir"
mkdir --mode=700 -- "$output_dir/input"
exec {output_fd}<"$output_dir"
output_ref="/proc/$$/fd/$output_fd"
output_identity="$(stat -Lc '%d:%i:%f:%u:%g' "/proc/$$/fd/$output_fd")"
[[ -d "$output_dir" && ! -L "$output_dir" ]] || fail "output path is not a directory"
[[ "$(stat -Lc '%a:%u:%g' "/proc/$$/fd/$output_fd")" == \
    "700:$(id -u):$(id -g)" ]] || fail "output directory ownership or mode is unsafe"
[[ "$(stat -c '%a:%u:%g' "$output_dir/input")" == \
    "700:$(id -u):$(id -g)" ]] || fail "input snapshot directory is unsafe"

run_dir="$(mktemp -d "${output_parent}/.tandem-agc-ooc-work.XXXXXX")"
chmod 700 "$run_dir"
mkdir --mode=700 -- "$run_dir/home" "$run_dir/tmp"
cleanup() {
    find "$run_dir" -depth -type f -delete 2>/dev/null || true
    find "$run_dir" -depth -type l -delete 2>/dev/null || true
    find "$run_dir" -depth -type d -empty -delete 2>/dev/null || true
}
trap cleanup EXIT

input_names=(
    tandem_cdc_lib.v
    tandem_agc_core.v
    tandem_agc_axi.v
    tandem_agc_axi.xdc
    axi_ooc.tcl
    validate_tandem_agc_ooc.py
    run_tandem_agc_ooc.sh
)
input_sources=(
    "$ROOT/hdl-tandem/tandem_cdc_lib.v"
    "$ROOT/hdl-tandem/tandem_agc_core.v"
    "$ROOT/hdl-tandem/tandem_agc_axi.v"
    "$ROOT/hdl-tandem/tandem_agc_axi.xdc"
    "$ROOT/hdl-tandem/axi_ooc.tcl"
    "$ROOT/scripts/validate_tandem_agc_ooc.py"
    "$ROOT/scripts/run_tandem_agc_ooc.sh"
)
input_git_paths=(
    hdl-tandem/tandem_cdc_lib.v
    hdl-tandem/tandem_agc_core.v
    hdl-tandem/tandem_agc_axi.v
    hdl-tandem/tandem_agc_axi.xdc
    hdl-tandem/axi_ooc.tcl
    scripts/validate_tandem_agc_ooc.py
    scripts/run_tandem_agc_ooc.sh
)

for index in "${!input_names[@]}"; do
    source_path=${input_sources[$index]}
    git_path=${input_git_paths[$index]}
    [[ -f "$source_path" && ! -L "$source_path" ]] ||
        fail "required OOC input is not a regular non-symlink: $source_path"
    git -C "$ROOT" show "${commit}:${git_path}" | cmp -s - "$source_path" ||
        fail "OOC input does not match its committed blob: $git_path"
    install -m 600 -- "$source_path" "$output_dir/input/${input_names[$index]}"
done

(
    cd "$output_dir/input"
    LC_ALL=C sha256sum "${input_names[@]}"
) >"$output_dir/.input-sha256.tmp"
mv -- "$output_dir/.input-sha256.tmp" "$output_dir/input-sha256.txt"

unset LD_PRELOAD PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
export LC_ALL=C LANG=C TZ=UTC HOME="$run_dir/home" TMPDIR="$run_dir/tmp"
export XILINX_LOCAL_USER_DATA=no
# shellcheck disable=SC1090
source "$CANONICAL_SETTINGS"
export LD_LIBRARY_PATH="$(dirname "$CANONICAL_LIBTINFO")${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
PATH=/usr/bin:/bin:/opt/Xilinx/Vivado/2022.2/bin
export PATH
[[ "$(realpath -- "$(command -v vivado)")" == "$CANONICAL_VIVADO" ]] ||
    fail "Vivado executable does not resolve to $CANONICAL_VIVADO"
[[ "$(sha256 "$CANONICAL_VIVADO")" == "$EXPECTED_VIVADO_SHA256" ]] ||
    fail "Vivado launcher hash does not match the qualified installation"

ldd /opt/Xilinx/Vivado/2022.2/lib/lnx64.o/librdi_commontasks.so \
    >"$output_dir/lib-resolution.txt"
resolved_libtinfo="$(awk '$1 == "libtinfo.so.5" {print $3}' \
    "$output_dir/lib-resolution.txt")"
[[ -n "$resolved_libtinfo" ]] || fail "Vivado runtime did not resolve libtinfo.so.5"
[[ "$(realpath -- "$resolved_libtinfo")" == "$CANONICAL_LIBTINFO" ]] ||
    fail "Vivado runtime resolved an unexpected libtinfo.so.5"

vivado_version="$(vivado -version)"
grep -Fxq "Vivado v2022.2 (64-bit)" <<<"$vivado_version" ||
    fail "Vivado version is not exactly v2022.2"
grep -Fxq "SW Build 3671981 on Fri Oct 14 04:59:54 MDT 2022" \
    <<<"$vivado_version" || fail "Vivado software build is not exactly 3671981"
grep -Fxq "IP Build 3669848 on Fri Oct 14 08:30:02 MDT 2022" \
    <<<"$vivado_version" || fail "Vivado IP build is not exactly 3669848"
printf '%s\n' "$vivado_version" >"$output_dir/.vivado-version.tmp"
mv -- "$output_dir/.vivado-version.tmp" "$output_dir/vivado-version.txt"

[[ -x "$CANONICAL_PYTHON" ]] || fail "canonical Python is not executable"
[[ "$(realpath -- "$CANONICAL_PYTHON")" == /usr/bin/python3.14 ]] ||
    fail "canonical Python does not resolve to /usr/bin/python3.14"
python_version="$(
    /usr/bin/env -u LD_LIBRARY_PATH "$CANONICAL_PYTHON" -I -B --version 2>&1
)"
[[ "$python_version" == "Python 3.14.4" ]] ||
    fail "OOC validator requires exact Python 3.14.4"
printf '%s\n' "$python_version" >"$output_dir/.python-version.tmp"
mv -- "$output_dir/.python-version.tmp" "$output_dir/python-version.txt"

branch="$(git -C "$ROOT" branch --show-current)"
{
    echo "schema=plutosdr-fw.tandem-agc-ooc.v1"
    echo "commit=${commit}"
    echo "branch=${branch}"
    echo "part=xc7z010clg400-1"
    echo "top=tandem_agc_axi"
    echo "events=1"
    echo "event_address_width=6"
    echo "event_record_width=128"
    echo "s_axi_aclk_period_ns=10.000"
    echo "l_clk_period_ns=16.276"
    echo "vivado_settings_sha256=${EXPECTED_SETTINGS_SHA256}"
    echo "vivado_launcher_sha256=${EXPECTED_VIVADO_SHA256}"
    echo "libtinfo_sha256=${EXPECTED_LIBTINFO_SHA256}"
    echo "python=${python_version}"
} >"$output_dir/.provenance.tmp"
mv -- "$output_dir/.provenance.tmp" "$output_dir/provenance.txt"

set +e
(
    cd "$run_dir"
    "$CANONICAL_VIVADO" -mode batch -nojournal -nolog -notrace \
        -source "$output_dir/input/axi_ooc.tcl" -tclargs "$output_dir"
) >"$output_dir/vivado.log" 2>&1
vivado_status=$?
set -e
[[ $vivado_status -eq 0 ]] || fail "Vivado OOC route failed (see $output_dir/vivado.log)"

[[ "$(git -C "$ROOT" rev-parse --verify HEAD)" == "$commit" ]] ||
    fail "firmware HEAD changed during OOC routing"
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] ||
    fail "firmware source tree changed during OOC routing"
for index in "${!input_names[@]}"; do
    cmp -s -- "${input_sources[$index]}" "$output_dir/input/${input_names[$index]}" ||
        fail "OOC input changed during routing: ${input_git_paths[$index]}"
done
(
    cd "$output_dir/input"
    sha256sum -c "$output_dir/input-sha256.txt"
) >/dev/null || fail "staged OOC input changed during routing"

[[ "$(stat -Lc '%d:%i:%f:%u:%g' "$output_dir")" == "$output_identity" ]] ||
    fail "output directory identity changed during routing"
[[ -d "$output_dir" && ! -L "$output_dir" ]] ||
    fail "output path became a symlink or non-directory during routing"
[[ "$(stat -c '%d:%i:%f:%u:%g' "$output_parent")" == "$parent_identity" ]] ||
    fail "output parent identity changed during routing"
[[ "$(stat -Lc '%a:%u:%g' "$output_dir")" == "700:$(id -u):$(id -g)" ]] ||
    fail "output directory ownership or mode changed during routing"
[[ -d "$output_ref/input" && ! -L "$output_ref/input" &&
   "$(stat -c '%a:%u:%g' "$output_ref/input")" == "700:$(id -u):$(id -g)" ]] ||
    fail "input snapshot directory changed during routing"

required=(
    utilization.rpt
    timing_summary.rpt
    cdc-summary.rpt
    cdc-details.rpt
    clock_interaction.rpt
    route_status.rpt
    drc.rpt
    methodology.rpt
    tandem_agc_axi_routed.dcp
)
for report in "${required[@]}"; do
    [[ -f "$output_ref/$report" && ! -L "$output_ref/$report" &&
       -s "$output_ref/$report" ]] || fail "missing safe OOC evidence: $report"
done

grep -Fq "=== TANDEM AXI ROUTE COMPLETE ===" "$output_ref/vivado.log" ||
    fail "Vivado log lacks the nonauthorizing route-complete marker"

if grep -Eiq '^[[:space:]]*(CRITICAL WARNING|ERROR|FATAL):' "$output_ref/vivado.log"; then
    fail "Vivado log contains an error, fatal, or critical warning"
fi

/usr/bin/env -u LD_LIBRARY_PATH /usr/bin/python3 -I -B \
    "$output_ref/input/validate_tandem_agc_ooc.py" \
    --directory-fd "$output_fd" \
    >"$output_ref/.timing-metrics.tmp" ||
    fail "strict routed OOC report validation failed"
mv -- "$output_ref/.timing-metrics.tmp" "$output_ref/timing-metrics.txt"

expected_inventory="$run_dir/expected-inventory.txt"
actual_inventory="$run_dir/actual-inventory.txt"
{
    echo "cdc-details.rpt f"
    echo "cdc-summary.rpt f"
    echo "clock_interaction.rpt f"
    echo "drc.rpt f"
    echo "input d"
    for name in "${input_names[@]}"; do echo "input/${name} f"; done
    echo "input-sha256.txt f"
    echo "lib-resolution.txt f"
    echo "methodology.rpt f"
    echo "provenance.txt f"
    echo "python-version.txt f"
    echo "route_status.rpt f"
    echo "tandem_agc_axi_routed.dcp f"
    echo "timing-metrics.txt f"
    echo "timing_summary.rpt f"
    echo "utilization.rpt f"
    echo "vivado-version.txt f"
    echo "vivado.log f"
} | LC_ALL=C sort >"$expected_inventory"
find "$output_ref" -mindepth 1 -maxdepth 2 -printf '%P %y\n' |
    LC_ALL=C sort >"$actual_inventory"
cmp -s -- "$expected_inventory" "$actual_inventory" ||
    fail "OOC evidence inventory is not exact before promotion"

while IFS= read -r -d '' evidence_file; do
    [[ ! -L "$evidence_file" && "$(stat -Lc '%F:%a:%u:%g' "$evidence_file")" == \
        "regular file:600:$(id -u):$(id -g)" ]] ||
        fail "unsafe OOC evidence file: $evidence_file"
done < <(find "$output_ref" -type f -print0)

(
    cd "$output_ref"
    find . -maxdepth 2 -type f ! -name evidence-sha256.txt ! -name status.txt \
        -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
) >"$run_dir/evidence-sha256.txt"
ln -- "$run_dir/evidence-sha256.txt" "$output_ref/evidence-sha256.txt" ||
    fail "could not claim the final evidence manifest"
unlink -- "$run_dir/evidence-sha256.txt"
manifest_sha256="$(sha256 "$output_ref/evidence-sha256.txt")"
{
    echo "schema=plutosdr-fw.tandem-agc-ooc-status.v1"
    echo "verdict=PASS"
    echo "scope=tandem_agc_axi_routed_ooc"
    echo "hardware_accessed=false"
    echo "firmware_release_eligible=false"
    echo "integrated_route_required=true"
    echo "commit=${commit}"
    echo "evidence_manifest_sha256=${manifest_sha256}"
} >"$run_dir/status.txt"

[[ "$(stat -Lc '%d:%i:%f:%u:%g' "$output_dir")" == "$output_identity" ]] ||
    fail "output directory identity changed during final promotion"
[[ -d "$output_dir" && ! -L "$output_dir" ]] ||
    fail "output path became a symlink or non-directory during final promotion"
[[ "$(stat -c '%d:%i:%f:%u:%g' "$output_parent")" == "$parent_identity" ]] ||
    fail "output parent identity changed during final promotion"
[[ "$(git -C "$ROOT" rev-parse --verify HEAD)" == "$commit" ]] ||
    fail "firmware HEAD changed during final promotion"
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] ||
    fail "firmware source tree changed during final promotion"
for index in "${!input_names[@]}"; do
    cmp -s -- "${input_sources[$index]}" \
        "$output_ref/input/${input_names[$index]}" ||
        fail "OOC input changed during final promotion: ${input_git_paths[$index]}"
done
(
    cd "$output_ref/input"
    LC_ALL=C sha256sum "${input_names[@]}"
) >"$run_dir/final-input-sha256.txt"
cmp -s -- "$run_dir/final-input-sha256.txt" "$output_ref/input-sha256.txt" ||
    fail "final staged OOC input hash inventory is not exact"
{
    cat "$expected_inventory"
    echo "evidence-sha256.txt f"
} | LC_ALL=C sort >"$run_dir/final-expected-inventory.txt"
find "$output_ref" -mindepth 1 -maxdepth 2 -printf '%P %y\n' |
    LC_ALL=C sort >"$run_dir/final-actual-inventory.txt"
cmp -s -- "$run_dir/final-expected-inventory.txt" \
    "$run_dir/final-actual-inventory.txt" ||
    fail "final OOC evidence inventory is not exact"
/usr/bin/env -u LD_LIBRARY_PATH /usr/bin/python3 -I -B \
    "$output_ref/input/validate_tandem_agc_ooc.py" \
    --directory-fd "$output_fd" \
    >"$run_dir/revalidated-timing-metrics.txt" ||
    fail "final strict routed OOC report validation failed"
cmp -s -- "$run_dir/revalidated-timing-metrics.txt" \
    "$output_ref/timing-metrics.txt" ||
    fail "final OOC report validation changed normalized timing evidence"
(
    cd "$output_ref"
    sha256sum -c evidence-sha256.txt
) >/dev/null || fail "final OOC evidence manifest does not verify"
while IFS= read -r -d '' evidence_file; do
    [[ ! -L "$evidence_file" && "$(stat -Lc '%F:%a:%u:%g' "$evidence_file")" == \
        "regular file:600:$(id -u):$(id -g)" ]] ||
        fail "unsafe final OOC evidence file: $evidence_file"
done < <(find "$output_ref" -type f -print0)
[[ "$(stat -Lc '%F:%a:%u:%g' "$output_ref")" == \
    "directory:700:$(id -u):$(id -g)" ]] ||
    fail "unsafe final OOC output directory"
[[ "$(stat -Lc '%F:%a:%u:%g' "$output_ref/input")" == \
    "directory:700:$(id -u):$(id -g)" ]] ||
    fail "unsafe final OOC input directory"
[[ "$(stat -Lc '%F:%a:%u:%g' "$run_dir/status.txt")" == \
    "regular file:600:$(id -u):$(id -g)" ]] ||
    fail "prepared PASS status is not a private regular file"
echo "All OOC checks complete at $output_dir; attempting final status claim"
# This NOREPLACE link is deliberately the final fallible operation.  No
# authorizing status exists if any prior validation or inventory check fails.
[[ "$(stat -Lc '%d:%i:%f:%u:%g' "$output_dir")" == "$output_identity" ]] ||
    fail "output directory identity changed immediately before status claim"
ln -- "$run_dir/status.txt" "/proc/$$/fd/$output_fd/status.txt"
