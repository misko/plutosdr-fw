#!/usr/bin/env bash
# Package and validate an already-built main-branch firmware tree.

set -euo pipefail
umask 0022

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_ROOT="${1:-}"
VIVADO_SETTINGS="${VIVADO_SETTINGS:-/opt/Xilinx/Vivado/2022.2/settings64.sh}"
MANIFEST="${SPF_GAIN_SERIES_MANIFEST:-${ROOT}/manifests/gain-series-v4-source.yaml}"
PACKAGE_STEM_PREFIX="${SPF_PACKAGE_STEM_PREFIX:-plutoplus-spf-main}"
RELEASE_STATE="${SPF_RELEASE_STATE:-main-ci}"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

[[ -n "$ARTIFACT_ROOT" ]] ||
    fail "usage: scripts/ci/package_main_firmware.sh /absolute/artifact/directory"
[[ "$ARTIFACT_ROOT" == /* ]] || fail "artifact directory must be absolute"
ARTIFACT_ROOT="$(realpath -m "$ARTIFACT_ROOT")"
mkdir -p "$ARTIFACT_ROOT"

cd "$ROOT"
[[ -f "$MANIFEST" ]] || fail "manifest not found: $MANIFEST"
initial_tracked_status="$(git status --porcelain --untracked-files=no)"
commit="$(git rev-parse HEAD)"
short_commit="$(git rev-parse --short=12 HEAD)"
stem="${PACKAGE_STEM_PREFIX}-${short_commit}"
dfu="${ARTIFACT_ROOT}/${stem}-pluto.dfu"
xsa="${ARTIFACT_ROOT}/${stem}-system_top.xsa"
rootfs="${ARTIFACT_ROOT}/${stem}-rootfs.cpio.gz"
provenance="${ARTIFACT_ROOT}/${stem}-provenance.txt"
bundle="${ARTIFACT_ROOT}/${stem}.tar.gz"
impl_dir="${ROOT}/hdl/projects/pluto/pluto.runs/impl_1"

required_outputs=(
    build/pluto.dfu
    build/system_top.xsa
    build/system_top.bit
    build/rootfs.cpio.gz
    buildroot/output/host/bin/mdir
    hdl/projects/pluto/pluto.sdk/system_top.xsa
    "${impl_dir}/system_top_routed.dcp"
    "${impl_dir}/system_top_timing_summary_routed.rpt"
)
for required in "${required_outputs[@]}"; do
    [[ -s "$required" ]] || fail "required build output is missing: $required"
done

cmp hdl/projects/pluto/pluto.sdk/system_top.xsa build/system_top.xsa
cp build/pluto.dfu "$dfu"
cp build/system_top.xsa "$xsa"
cp build/rootfs.cpio.gz "$rootfs"
cp "$MANIFEST" "$ARTIFACT_ROOT/$(basename "$MANIFEST")"

dfu-suffix -c "$dfu" 2>&1 | tee "$ARTIFACT_ROOT/dfu-suffix-check.txt"
grep -Eq 'Vendor ID:[[:space:]]+0x0456' "$ARTIFACT_ROOT/dfu-suffix-check.txt" ||
    fail "DFU vendor ID is not 0x0456"
grep -Eq 'Product ID:[[:space:]]+0xB673' "$ARTIFACT_ROOT/dfu-suffix-check.txt" ||
    fail "DFU product ID is not 0xB673"
grep -Eq 'Length:[[:space:]]+16$' "$ARTIFACT_ROOT/dfu-suffix-check.txt" ||
    fail "DFU suffix length is not 16"

dumpimage -l "$dfu" 2>&1 | tee "$ARTIFACT_ROOT/fit-layout.txt"
fdt_count="$(awk '$1 == "Image" && $3 ~ /^\(fdt@/ {count++} END {print count+0}' \
    "$ARTIFACT_ROOT/fit-layout.txt")"
fpga_count="$(awk '$1 == "Image" && $3 == "(fpga@1)" {count++} END {print count+0}' \
    "$ARTIFACT_ROOT/fit-layout.txt")"
kernel_count="$(awk '$1 == "Image" && $3 == "(linux_kernel@1)" {count++} END {print count+0}' \
    "$ARTIFACT_ROOT/fit-layout.txt")"
ramdisk_count="$(awk '$1 == "Image" && $3 == "(ramdisk@1)" {count++} END {print count+0}' \
    "$ARTIFACT_ROOT/fit-layout.txt")"
[[ "$fdt_count" == 3 && "$fpga_count" == 1 && "$kernel_count" == 1 &&
   "$ramdisk_count" == 1 ]] ||
    fail "unexpected FIT layout: fdt=$fdt_count fpga=$fpga_count kernel=$kernel_count ramdisk=$ramdisk_count"

ramdisk_index="$(awk '$1 == "Image" && $3 == "(ramdisk@1)" {print $2}' \
    "$ARTIFACT_ROOT/fit-layout.txt")"
[[ -n "$ramdisk_index" ]] || fail "could not locate the FIT ramdisk index"
dumpimage -T flat_dt -p "$ramdisk_index" \
    -o "$ARTIFACT_ROOT/packed-rootfs.cpio.gz" "$dfu"
cmp "$rootfs" "$ARTIFACT_ROOT/packed-rootfs.cpio.gz"

unzip -l "$xsa" | tee "$ARTIFACT_ROOT/xsa-layout.txt"
unzip -Z1 "$xsa" | grep -Fxq system_top.bit ||
    fail "XSA does not contain system_top.bit"
unzip -p "$xsa" system_top.bit |
    sha256sum | sed 's/[[:space:]]*-$//' > "$ARTIFACT_ROOT/system-top-bit.sha256"

rootfs_check="${ARTIFACT_ROOT}/rootfs-check"
mkdir -p "$rootfs_check"
(
    cd "$rootfs_check"
    gzip -dc "$rootfs" | cpio --quiet -idm \
        opt/VERSIONS opt/vfat.img \
        usr/sbin/sdr_usb_gadget usr/sbin/sdr_ip_gadget
)
cp "$rootfs_check/opt/VERSIONS" "$ARTIFACT_ROOT/packed-VERSIONS.txt"
file "$rootfs_check/usr/sbin/sdr_usb_gadget" \
     "$rootfs_check/usr/sbin/sdr_ip_gadget" |
    tee "$ARTIFACT_ROOT/gadget-binaries.txt"
[[ "$(grep -c 'ELF 32-bit.*ARM.*EABI5' "$ARTIFACT_ROOT/gadget-binaries.txt")" == 2 ]] ||
    fail "packaged gadget binaries are not both ARM EABI5 executables"
buildroot/output/host/bin/mdir -i "$rootfs_check/opt/vfat.img@@512" :: |
    tee "$ARTIFACT_ROOT/packed-vfat-listing.txt"
grep -qi 'index.html' "$ARTIFACT_ROOT/packed-vfat-listing.txt" ||
    fail "mass-storage filesystem lacks index.html"
grep -qi 'LICENSE.html' "$ARTIFACT_ROOT/packed-vfat-listing.txt" ||
    fail "mass-storage filesystem lacks LICENSE.html"

for report in \
    system_top_timing_summary_routed.rpt \
    system_top_route_status.rpt \
    system_top_drc_routed.rpt \
    system_top_methodology_drc_routed.rpt; do
    [[ -s "$impl_dir/$report" ]] || fail "Vivado report is missing: $report"
    cp "$impl_dir/$report" "$ARTIFACT_ROOT/$report"
done
grep -Fq 'All user specified timing constraints are met.' \
    "$ARTIFACT_ROOT/system_top_timing_summary_routed.rpt" ||
    fail "routed timing constraints are not met"

cat > "$ARTIFACT_ROOT/post-route-reports.tcl" <<EOF
open_checkpoint {$impl_dir/system_top_routed.dcp}
report_cdc -details -file {$ARTIFACT_ROOT/system_top_cdc_routed.rpt}
report_bus_skew -file {$ARTIFACT_ROOT/system_top_bus_skew_routed.rpt}
exit
EOF
(
    # shellcheck source=/dev/null
    source "$VIVADO_SETTINGS"
    vivado -mode batch \
        -source "$ARTIFACT_ROOT/post-route-reports.tcl" \
        -log "$ARTIFACT_ROOT/post-route-vivado.log" \
        -journal "$ARTIFACT_ROOT/post-route-vivado.jou"
)
[[ -s "$ARTIFACT_ROOT/system_top_cdc_routed.rpt" ]] ||
    fail "Vivado did not produce the routed CDC report"
[[ -s "$ARTIFACT_ROOT/system_top_bus_skew_routed.rpt" ]] ||
    fail "Vivado did not produce the routed bus-skew report"
if grep -Eq '^CDC-10[[:space:]]' "$ARTIFACT_ROOT/system_top_cdc_routed.rpt"; then
    fail "routed CDC report contains CDC-10 combinational-before-sync paths"
fi
[[ "$(grep -c 'Slack (MET)' "$ARTIFACT_ROOT/system_top_bus_skew_routed.rpt")" -ge 4 ]] ||
    fail "fewer than four bus-skew constraints report MET"
if grep -q 'Slack (VIOLATED)' "$ARTIFACT_ROOT/system_top_bus_skew_routed.rpt"; then
    fail "a timestamp FIFO bus-skew constraint is violated"
fi

critical_warnings="$(grep -c '^CRITICAL WARNING:' hdl/projects/pluto/vivado.log || true)"
[[ "$critical_warnings" == 0 ]] ||
    fail "top-level Vivado log contains $critical_warnings critical warnings"
tar -C hdl/projects/pluto -czf "$ARTIFACT_ROOT/vivado-logs.tar.gz" \
    vivado.log vivado.jou pluto.runs

timing_values="$(awk '/WNS\(ns\)/ {getline; getline; print; exit}' \
    "$ARTIFACT_ROOT/system_top_timing_summary_routed.rpt")"
read -r wns tns tns_failing _ whs ths ths_failing _ wpws tpws tpws_failing _ \
    <<< "$timing_values"
[[ "${tns_failing:-missing}" == 0 && "${ths_failing:-missing}" == 0 &&
   "${tpws_failing:-missing}" == 0 ]] ||
    fail "timing report contains failing endpoints"

(
    cd "$ARTIFACT_ROOT"
    sha256sum \
        "$(basename "$dfu")" \
        "$(basename "$xsa")" \
        "$(basename "$rootfs")" \
        vivado-logs.tar.gz > PAYLOAD_SHA256SUMS
)

{
    echo "release_state=$RELEASE_STATE"
    echo 'hardware_tested=false'
    echo 'hardware_accessed=false'
    echo 'intended_boot_mode=RAM-only-until-hardware-promotion'
    echo "firmware_source=$commit"
    echo "source_ref=${GITHUB_REF:-local}"
    echo "source_event=${GITHUB_EVENT_NAME:-local}"
    echo "github_run_id=${GITHUB_RUN_ID:-local}"
    echo "github_run_attempt=${GITHUB_RUN_ATTEMPT:-local}"
    echo "build_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "build_duration_seconds=${CI_BUILD_DURATION_SECONDS:-unknown}"
    echo "builder_host=$(hostname)"
    echo "builder_arch=$(uname -m)"
    echo "source_date_epoch=${SOURCE_DATE_EPOCH:-unset}"
    # shellcheck source=/dev/null
    source "$VIVADO_SETTINGS"
    vivado -version | sed -n '1,3p'
    echo
    echo '[submodules]'
    git submodule status --recursive
    echo
    echo '[payload SHA-256]'
    cat "$ARTIFACT_ROOT/PAYLOAD_SHA256SUMS"
    echo "system_top.bit $(awk '{print $1}' "$ARTIFACT_ROOT/system-top-bit.sha256")"
    echo
    echo '[routed timing]'
    echo "WNS=$wns TNS=$tns TNS_failing_endpoints=$tns_failing"
    echo "WHS=$whs THS=$ths THS_failing_endpoints=$ths_failing"
    echo "WPWS=$wpws TPWS=$tpws TPWS_failing_endpoints=$tpws_failing"
    echo
    echo '[packaged /opt/VERSIONS]'
    cat "$ARTIFACT_ROOT/packed-VERSIONS.txt"
} > "$provenance"

{
    echo "Candidate: $stem"
    echo "Firmware source: $commit"
    echo 'Validation state: PASS OFFLINE / HARDWARE UNTESTED'
    echo
    echo 'PASS source graph, host preflight, and coherent-counter simulation'
    echo 'PASS clean Vivado FPGA rebuild and XSA export'
    echo "PASS routed timing: WNS $wns ns, WHS $whs ns"
    echo 'PASS timestamp FIFO bus-skew constraints'
    echo 'PASS no CDC-10 combinational-before-synchronizer paths'
    echo 'PASS DFU suffix, FIT layout, XSA layout, and packaged-rootfs identity'
    echo 'PASS packaged ARM gadget binaries and mass-storage legal page'
    echo 'PASS final SHA-256 verification'
    echo
    echo 'This package has not accessed or been tested on radio hardware.'
    echo 'It must remain RAM-boot only until the hardware promotion gates pass.'
} > "$ARTIFACT_ROOT/offline-validation-summary.txt"

final_tracked_status="$(git status --porcelain --untracked-files=no)"
[[ "$final_tracked_status" == "$initial_tracked_status" ]] ||
    fail "tracked source tree changed while packaging"
git status --short --branch > "$ARTIFACT_ROOT/git-status.txt"

mapfile -t checksum_files < <(
    cd "$ARTIFACT_ROOT"
    find . -maxdepth 1 -type f \
        ! -name SHA256SUMS \
        ! -name bundle-contents.txt \
        ! -name "$(basename "$bundle")" \
        ! -name "$(basename "$bundle").sha256" \
        -printf '%f\n' | sort
)
(
    cd "$ARTIFACT_ROOT"
    sha256sum "${checksum_files[@]}" > SHA256SUMS
    sha256sum -c SHA256SUMS
)

(
    cd "$ARTIFACT_ROOT"
    mapfile -t bundle_files < <(find . -maxdepth 1 -type f \
        ! -name bundle-contents.txt \
        ! -name "$(basename "$bundle")" \
        ! -name "$(basename "$bundle").sha256" \
        -printf '%f\n' | sort)
    printf '%s\n' "${bundle_files[@]}" > bundle-contents.txt
    tar --sort=name --mtime="@${SOURCE_DATE_EPOCH:-0}" \
        --owner=0 --group=0 --numeric-owner \
        -cf - -T bundle-contents.txt | gzip -n > "$(basename "$bundle")"
    sha256sum "$(basename "$bundle")" > "$(basename "$bundle").sha256"
    sha256sum -c "$(basename "$bundle").sha256"
)

printf 'Deployment bundle: %s\n' "$bundle"
