#!/usr/bin/env bash
# Package and validate an already-built main-branch firmware tree.

set -euo pipefail
umask 0022

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_ROOT="${1:-}"
VIVADO_SETTINGS="${VIVADO_SETTINGS:-/opt/Xilinx/Vivado/2022.2/settings64.sh}"
MANIFEST="${SPF_GAIN_SERIES_MANIFEST:-${ROOT}/manifests/libiio-frame-metadata-v5-source.yaml}"
INTEGRATED_WAIVERS="${SPF_INTEGRATED_WAIVERS:-}"
PACKAGE_STEM_PREFIX="${SPF_PACKAGE_STEM_PREFIX:-plutoplus-spf-main}"
RELEASE_STATE="${SPF_RELEASE_STATE:-main-ci}"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

# RC5 through RC32, the final v8 route, and the current main integration are
# protected builds and therefore
# cannot opt out of the reviewed integrated-route inventory. Other historical
# source locks retain their original package path unless a waiver inventory is
# explicitly supplied by their trusted workflow.
case "$(basename "$MANIFEST")" in
ddr-ring-v1-rc2-source.yaml | ddr-ring-v1-rc1-source.yaml | ddr-burst-v2-rc3-source.yaml | ddr-burst-v2-rc2-source.yaml | ddr-burst-v2-rc1-source.yaml | ddr-burst-v1-rc5-source.yaml | ddr-burst-v1-rc4-source.yaml | ddr-burst-v1-rc3-source.yaml | \
tandem-agc-v8-rc5-source.yaml | tandem-agc-v8-rc6-source.yaml | tandem-agc-v8-rc7-source.yaml | tandem-agc-v8-rc8-source.yaml | tandem-agc-v8-rc9-source.yaml | tandem-agc-v8-rc10-source.yaml | tandem-agc-v8-rc11-source.yaml | tandem-agc-v8-rc12-source.yaml | tandem-agc-v8-rc13-source.yaml | tandem-agc-v8-rc14-source.yaml | tandem-agc-v8-rc15-source.yaml | tandem-agc-v8-rc16-source.yaml | tandem-agc-v8-rc17-source.yaml | tandem-agc-v8-rc18-source.yaml | tandem-agc-v8-rc19-source.yaml | tandem-agc-v8-rc20-source.yaml | tandem-agc-v8-rc21-source.yaml | tandem-agc-v8-rc22-source.yaml | tandem-agc-v8-rc23-source.yaml | tandem-agc-v8-rc24-source.yaml | tandem-agc-v8-rc25-source.yaml | tandem-agc-v8-rc26-source.yaml | tandem-agc-v8-rc27-source.yaml | tandem-agc-v8-rc28-source.yaml | tandem-agc-v8-rc29-source.yaml | tandem-agc-v8-rc30-source.yaml | tandem-agc-v8-rc31-source.yaml | tandem-agc-v8-rc32-source.yaml | tandem-agc-v8-source.yaml | metadata-timeout-main-v1-source.yaml | single-rx-metadata-rc1-source.yaml | ddr-burst-v1-rc1-source.yaml | ddr-burst-v1-rc2-source.yaml)
    manifest_name="$(basename -- "$MANIFEST")"
    canonical_manifest="${ROOT}/manifests/${manifest_name}"
    [[ -f "$MANIFEST" && "$(realpath -- "$MANIFEST")" == "$canonical_manifest" ]] ||
        fail "protected manifest must use the canonical repository path: ${canonical_manifest}"
    git --no-replace-objects -C "$ROOT" show "HEAD:manifests/${manifest_name}" |
        cmp -s - "$canonical_manifest" ||
        fail "protected manifest differs from its committed HEAD blob"
    # The release-authorizing source graph pins the one reviewed inventory by
    # repository path; an ambient environment variable cannot broaden it.
    INTEGRATED_WAIVERS="${ROOT}/manifests/tandem-agc-v8-integrated-waivers.json"
    ;;
esac

[[ -n "$ARTIFACT_ROOT" ]] ||
    fail "usage: scripts/ci/package_main_firmware.sh /absolute/artifact/directory"
[[ "$ARTIFACT_ROOT" == /* ]] || fail "artifact directory must be absolute"
ARTIFACT_ROOT="$(realpath -m "$ARTIFACT_ROOT")"
mkdir -p "$ARTIFACT_ROOT"

cd "$ROOT"
[[ -f "$MANIFEST" ]] || fail "manifest not found: $MANIFEST"
if [[ -n "$INTEGRATED_WAIVERS" ]]; then
    [[ -f "$INTEGRATED_WAIVERS" ]] ||
        fail "integrated waiver inventory not found: $INTEGRATED_WAIVERS"
fi
initial_source_status="$(git status --porcelain --untracked-files=all)"
if [[ -n "$INTEGRATED_WAIVERS" && -n "$initial_source_status" ]]; then
    fail "release-authorizing package requires a completely clean source tree"
fi
commit="$(git rev-parse HEAD)"
short_commit="$(git rev-parse --short=12 HEAD)"
stem="${PACKAGE_STEM_PREFIX}-${short_commit}"
dfu="${ARTIFACT_ROOT}/${stem}-pluto.dfu"
frm="${ARTIFACT_ROOT}/${stem}-pluto.frm"
xsa="${ARTIFACT_ROOT}/${stem}-system_top.xsa"
rootfs="${ARTIFACT_ROOT}/${stem}-rootfs.cpio.gz"
provenance="${ARTIFACT_ROOT}/${stem}-provenance.txt"
bundle="${ARTIFACT_ROOT}/${stem}.tar.gz"
impl_dir="${ROOT}/hdl/projects/pluto/pluto.runs/impl_1"
manifest_copy="${ARTIFACT_ROOT}/$(basename "$MANIFEST")"
waiver_copy=''
if [[ -n "$INTEGRATED_WAIVERS" ]]; then
    waiver_copy="${ARTIFACT_ROOT}/$(basename "$INTEGRATED_WAIVERS")"
fi
routed_dcp="${ARTIFACT_ROOT}/system_top_routed.dcp"
integrated_verdict="${ARTIFACT_ROOT}/integrated-release-verdict.json"

required_outputs=(
    build/pluto.dfu
    build/pluto.frm
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
cp build/pluto.frm "$frm"
cp build/system_top.xsa "$xsa"
cp build/rootfs.cpio.gz "$rootfs"
cp "$MANIFEST" "$manifest_copy"
if [[ -n "$INTEGRATED_WAIVERS" ]]; then
    cp "$INTEGRATED_WAIVERS" "$waiver_copy"
fi
cp "$impl_dir/system_top_routed.dcp" "$routed_dcp"

dfu-suffix -c "$dfu" 2>&1 | tee "$ARTIFACT_ROOT/dfu-suffix-check.txt"
grep -Eq 'Vendor ID:[[:space:]]+0x0456' "$ARTIFACT_ROOT/dfu-suffix-check.txt" ||
    fail "DFU vendor ID is not 0x0456"
grep -Eq 'Product ID:[[:space:]]+0xB673' "$ARTIFACT_ROOT/dfu-suffix-check.txt" ||
    fail "DFU product ID is not 0xB673"
grep -Eq 'Length:[[:space:]]+16$' "$ARTIFACT_ROOT/dfu-suffix-check.txt" ||
    fail "DFU suffix length is not 16"

# The persistent mass-storage image and the RAM-only DFU must contain the exact
# same FIT bytes. The only permitted difference is their format-specific
# trailer: a 16-byte DFU suffix versus a 32-hex-character MD5 plus newline.
dfu_bytes="$(stat -c %s "$dfu")"
frm_bytes="$(stat -c %s "$frm")"
[[ "$dfu_bytes" -gt 16 && "$frm_bytes" -gt 33 ]] ||
    fail "DFU/FRM is too small to contain its required trailer"
dfu_fit_bytes="$((dfu_bytes - 16))"
frm_fit_bytes="$((frm_bytes - 33))"
[[ "$dfu_fit_bytes" == "$frm_fit_bytes" ]] ||
    fail "DFU and FRM do not carry the same FIT length"
cmp -n "$dfu_fit_bytes" "$dfu" "$frm" ||
    fail "DFU and FRM do not carry identical FIT bytes"
frm_body_md5="$(head -c "$frm_fit_bytes" "$frm" | md5sum | awk '{print $1}')"
frm_trailer_md5="$(tail -c 33 "$frm" | tr -d '\n')"
[[ "$frm_trailer_md5" =~ ^[0-9a-f]{32}$ &&
   "$frm_trailer_md5" == "$frm_body_md5" ]] ||
    fail "FRM MD5 trailer does not authenticate its FIT body"
{
    echo "fit_bytes=$frm_fit_bytes"
    echo "fit_md5=$frm_body_md5"
    echo 'dfu_fit_matches_frm=true'
} > "$ARTIFACT_ROOT/frm-layout.txt"

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
fpga_index="$(awk '$1 == "Image" && $3 == "(fpga@1)" {print $2}' \
    "$ARTIFACT_ROOT/fit-layout.txt")"
[[ -n "$ramdisk_index" ]] || fail "could not locate the FIT ramdisk index"
[[ -n "$fpga_index" ]] || fail "could not locate the FIT FPGA index"
dumpimage -T flat_dt -p "$ramdisk_index" \
    -o "$ARTIFACT_ROOT/packed-rootfs.cpio.gz" "$dfu"
cmp "$rootfs" "$ARTIFACT_ROOT/packed-rootfs.cpio.gz"

unzip -l "$xsa" | tee "$ARTIFACT_ROOT/xsa-layout.txt"
unzip -Z1 "$xsa" | grep -Fxq system_top.bit ||
    fail "XSA does not contain system_top.bit"
unzip -p "$xsa" system_top.bit > "$ARTIFACT_ROOT/system_top.bit"
[[ -s "$ARTIFACT_ROOT/system_top.bit" ]] ||
    fail "XSA system_top.bit extraction is empty"
dumpimage -T flat_dt -p "$fpga_index" \
    -o "$ARTIFACT_ROOT/packed-fpga.bit" "$dfu"
cmp "$ARTIFACT_ROOT/system_top.bit" "$ARTIFACT_ROOT/packed-fpga.bit" ||
    fail "DFU FPGA payload differs from the qualified XSA bitstream"
(
    cd "$ARTIFACT_ROOT"
    sha256sum system_top.bit > system-top-bit.sha256
)

rootfs_check="${ARTIFACT_ROOT}/rootfs-check"
mkdir -p "$rootfs_check"
(
    cd "$rootfs_check"
    gzip -dc "$rootfs" | cpio --quiet -idm \
        opt/VERSIONS opt/vfat.img \
        usr/sbin/sdr_usb_gadget usr/sbin/sdr_ip_gadget \
        usr/sbin/pluto-mute-tx etc/init.d/S23udc
)
cp "$rootfs_check/opt/VERSIONS" "$ARTIFACT_ROOT/packed-VERSIONS.txt"

# A source manifest may pin the human-readable component identities expected
# in /opt/VERSIONS in addition to their commit graph.  This catches stale or
# ambiguous persistent-runner tags before an artifact can be qualified.
manifest_value() {
    local key=$1 value
    value="$(sed -n "s/^${key}:[[:space:]]*//p" "$MANIFEST" | head -1)"
    printf '%s' "${value%"${value##*[![:space:]]}"}"
}
for identity in \
    "hdl:versions_hdl" \
    "buildroot:versions_buildroot" \
    "linux:versions_linux" \
    "u-boot-xlnx:versions_u_boot_xlnx"; do
    IFS=: read -r field key <<<"$identity"
    expected_identity="$(manifest_value "$key")"
    [[ -n "$expected_identity" ]] || continue
    packed_identity="$(awk -v field="$field" '$1 == field {print $2; exit}' \
        "$ARTIFACT_ROOT/packed-VERSIONS.txt")"
    [[ "$packed_identity" == "$expected_identity" ]] ||
        fail "packed $field identity is '$packed_identity'; manifest requires '$expected_identity'"
    printf 'Component identity pin satisfied: %s %s\n' \
        "$field" "$expected_identity"
done

# The version a radio will report about itself. This file has always been
# extracted and printed here; what was missing was anyone comparing it to the
# name the build was supposed to produce. Both fingerprint-v3 and
# gain-series-v4-rc17 shipped stamped with the PREVIOUS release's name, and in
# both cases the wrong string was sitting in this artifact the whole time.
#
# verify_release.sh cannot catch this: it compares the DFU against a manifest
# written afterwards from whatever the DFU happens to say, so it detects
# tampering, not mislabelling. The check has to happen here, at build time.
packed_version="$(awk '$1 == "device-fw" {print $2; exit}' \
    "$ARTIFACT_ROOT/packed-VERSIONS.txt")"
[[ -n "$packed_version" ]] ||
    fail "packaged /opt/VERSIONS has no device-fw line"
printf 'Packaged device-fw: %s\n' "$packed_version"
protected_version=''
case "$(basename "$MANIFEST"):$RELEASE_STATE" in
tandem-agc-v8-rc5-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc5'
    ;;
tandem-agc-v8-rc6-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc6'
    ;;
tandem-agc-v8-rc7-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc7'
    ;;
tandem-agc-v8-rc8-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc8'
    ;;
tandem-agc-v8-rc9-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc9'
    ;;
tandem-agc-v8-rc10-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc10'
    ;;
tandem-agc-v8-rc11-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc11'
    ;;
tandem-agc-v8-rc12-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc12'
    ;;
tandem-agc-v8-rc13-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc13'
    ;;
tandem-agc-v8-rc14-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc14'
    ;;
tandem-agc-v8-rc15-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc15'
    ;;
tandem-agc-v8-rc16-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc16'
    ;;
tandem-agc-v8-rc17-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc17'
    ;;
tandem-agc-v8-rc18-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc18'
    ;;
tandem-agc-v8-rc19-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc19'
    ;;
tandem-agc-v8-rc20-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc20'
    ;;
tandem-agc-v8-rc21-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc21'
    ;;
tandem-agc-v8-rc22-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc22'
    ;;
tandem-agc-v8-rc23-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc23'
    ;;
tandem-agc-v8-rc24-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc24'
    ;;
tandem-agc-v8-rc25-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc25'
    ;;
tandem-agc-v8-rc26-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc26'
    ;;
tandem-agc-v8-rc27-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc27'
    ;;
tandem-agc-v8-rc28-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc28'
    ;;
tandem-agc-v8-rc29-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc29'
    ;;
tandem-agc-v8-rc30-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc30'
    ;;
tandem-agc-v8-rc31-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc31'
    ;;
tandem-agc-v8-rc32-source.yaml:*)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8-rc32'
    ;;
single-rx-metadata-rc1-source.yaml:*)
    protected_version='v0.42-plutoplus-spf-single-rx-metadata-rc1'
    ;;
ddr-burst-v1-rc1-source.yaml:*)
    protected_version='v0.42-plutoplus-spf-ddr-burst-v1-rc1'
    ;;
ddr-burst-v1-rc2-source.yaml:candidate)
    protected_version='v0.42-plutoplus-spf-ddr-burst-v1-rc2'
    ;;
ddr-burst-v1-rc3-source.yaml:candidate)
    protected_version='v0.42-plutoplus-spf-ddr-burst-v1-rc3'
    ;;
ddr-burst-v1-rc4-source.yaml:candidate)
    protected_version='v0.42-plutoplus-spf-ddr-burst-v1-rc4'
    ;;
ddr-burst-v1-rc5-source.yaml:candidate)
    protected_version='v0.42-plutoplus-spf-ddr-burst-v1-rc5'
    ;;
ddr-burst-v2-rc1-source.yaml:candidate)
    protected_version='v0.42-plutoplus-spf-ddr-burst-v2-rc1'
    ;;
ddr-burst-v2-rc2-source.yaml:candidate)
    protected_version='v0.42-plutoplus-spf-ddr-burst-v2-rc2'
    ;;
ddr-burst-v2-rc3-source.yaml:candidate)
    protected_version='v0.42-plutoplus-spf-ddr-burst-v2-rc3'
    ;;
ddr-ring-v1-rc1-source.yaml:candidate)
    protected_version='v0.43-plutoplus-spf-ddr-ring-v1-rc1'
    ;;
ddr-ring-v1-rc2-source.yaml:candidate)
    protected_version='v0.43-plutoplus-spf-ddr-ring-v1-rc2'
    ;;
tandem-agc-v8-source.yaml:final-release)
    protected_version='v0.41-plutoplus-spf-tandem-agc-v8'
    ;;
esac
if [[ -n "$protected_version" && "${RELEASE_VERSION:-}" != "$protected_version" ]]; then
    fail "protected route requires RELEASE_VERSION=${protected_version}"
fi
if [[ -n "${RELEASE_VERSION:-}" ]]; then
    [[ "$packed_version" == "$RELEASE_VERSION" ]] ||
        fail "packaged device-fw is '${packed_version}' but RELEASE_VERSION requested '${RELEASE_VERSION}'"
    printf 'Version pin satisfied: %s\n' "$RELEASE_VERSION"
else
    # Not a failure -- development builds legitimately describe as N commits
    # past a tag -- but it must be visible, because a release built without the
    # pin is exactly how the last two mislabelled images were produced.
    case "$packed_version" in
    *-dirty)
        fail "packaged device-fw '${packed_version}' was built from a dirty tree" ;;
    *-g*)
        printf 'NOTE: device-fw is not an exact tag (%s).\n' "$packed_version"
        printf '      Set RELEASE_VERSION for any build intended for release.\n' ;;
    esac
fi
file "$rootfs_check/usr/sbin/sdr_usb_gadget" \
     "$rootfs_check/usr/sbin/sdr_ip_gadget" |
    tee "$ARTIFACT_ROOT/gadget-binaries.txt"
[[ "$(grep -c 'ELF 32-bit.*ARM.*EABI5' "$ARTIFACT_ROOT/gadget-binaries.txt")" == 2 ]] ||
    fail "packaged gadget binaries are not both ARM EABI5 executables"
[[ -x "$rootfs_check/usr/sbin/pluto-mute-tx" ]] ||
    fail "packaged TX mute helper is missing or not executable"
grep -Fq "printf '%s\\n' '-80'" "$rootfs_check/usr/sbin/pluto-mute-tx" ||
    fail "packaged TX mute helper does not request exactly -80 dB"
mute_line="$(grep -n -m1 '/usr/sbin/pluto-mute-tx' \
    "$rootfs_check/etc/init.d/S23udc" | cut -d: -f1)"
bind_line="$(grep -n -m1 'echo ci_hdrc.0 > $GADGET/UDC' \
    "$rootfs_check/etc/init.d/S23udc" | cut -d: -f1)"
[[ -n "$mute_line" && -n "$bind_line" && "$mute_line" -lt "$bind_line" ]] ||
    fail "packaged startup does not mute TX before binding USB"
buildroot/output/host/bin/mdir -i "$rootfs_check/opt/vfat.img@@512" :: |
    tee "$ARTIFACT_ROOT/packed-vfat-listing.txt"
grep -qi 'index.html' "$ARTIFACT_ROOT/packed-vfat-listing.txt" ||
    fail "mass-storage filesystem lacks index.html"
grep -qi 'LICENSE.html' "$ARTIFACT_ROOT/packed-vfat-listing.txt" ||
    fail "mass-storage filesystem lacks LICENSE.html"

cat > "$ARTIFACT_ROOT/post-route-reports.tcl" <<EOF
open_checkpoint {$routed_dcp}
set spf_version_text [version]
if {![regexp {Vivado v([0-9.]+)} \$spf_version_text -> spf_tool_version]} {
    error {cannot resolve Vivado version for routed-report provenance}
}
if {![regexp {SW Build ([0-9]+)} \$spf_version_text -> spf_tool_build]} {
    error {cannot resolve Vivado build for routed-report provenance}
}
set spf_design [get_property TOP [current_design]]
set spf_device [get_property PART [current_design]]
set spf_route_report [report_route_status -return_string]
if {![regexp {# of routable nets[.]+[[:space:]]*:[[:space:]]*([0-9]+)[[:space:]]*:} \$spf_route_report -> spf_routable]} {
    error {cannot resolve routable-net inventory}
}
if {![regexp {# of fully routed nets[.]+[[:space:]]*:[[:space:]]*([0-9]+)[[:space:]]*:} \$spf_route_report -> spf_fully_routed]} {
    error {cannot resolve fully-routed-net inventory}
}
if {![regexp {# of nets with routing errors[.]+[[:space:]]*:[[:space:]]*([0-9]+)[[:space:]]*:} \$spf_route_report -> spf_route_errors]} {
    error {cannot resolve routing-error inventory}
}
if {\$spf_routable <= 0 || \$spf_fully_routed != \$spf_routable || \$spf_route_errors != 0} {
    error {checkpoint is not fully routed}
}
set spf_route_fd [open {$ARTIFACT_ROOT/system_top_route_status.rpt} w]
puts \$spf_route_fd "| Tool Version : Vivado v.\$spf_tool_version (lin64) Build \$spf_tool_build generated"
puts \$spf_route_fd "| Design       : \$spf_design"
puts \$spf_route_fd "| Device       : \$spf_device"
puts \$spf_route_fd {| Design State : Fully Routed}
puts -nonewline \$spf_route_fd \$spf_route_report
close \$spf_route_fd
report_drc -file {$ARTIFACT_ROOT/system_top_drc_routed.rpt}
report_methodology -file {$ARTIFACT_ROOT/system_top_methodology_drc_routed.rpt}
report_utilization -file {$ARTIFACT_ROOT/system_top_utilization_routed.rpt}
report_timing_summary -max_paths 10 -report_unconstrained -warn_on_violation -file {$ARTIFACT_ROOT/system_top_timing_summary_routed.rpt}
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
for report in \
    system_top_timing_summary_routed.rpt \
    system_top_route_status.rpt \
    system_top_drc_routed.rpt \
    system_top_methodology_drc_routed.rpt \
    system_top_utilization_routed.rpt \
    system_top_cdc_routed.rpt \
    system_top_bus_skew_routed.rpt; do
    [[ -s "$ARTIFACT_ROOT/$report" ]] ||
        fail "Vivado did not regenerate the routed report from the packaged DCP: $report"
done
grep -Fq 'All user specified timing constraints are met.' \
    "$ARTIFACT_ROOT/system_top_timing_summary_routed.rpt" ||
    fail "routed timing constraints are not met"
if grep -Eq '^CDC-10[[:space:]]' "$ARTIFACT_ROOT/system_top_cdc_routed.rpt"; then
    fail "routed CDC report contains CDC-10 combinational-before-sync paths"
fi
[[ "$(grep -c 'Slack (MET)' "$ARTIFACT_ROOT/system_top_bus_skew_routed.rpt")" -ge 4 ]] ||
    fail "fewer than four bus-skew constraints report MET"
if grep -q 'Slack (VIOLATED)' "$ARTIFACT_ROOT/system_top_bus_skew_routed.rpt"; then
    fail "a timestamp FIFO bus-skew constraint is violated"
fi

if [[ -n "$INTEGRATED_WAIVERS" ]]; then
    python3 scripts/validate_integrated_release.py \
        --source-commit "$commit" \
        --source-manifest "$manifest_copy" \
        --waiver-inventory "$waiver_copy" \
        --routed-dcp "$routed_dcp" \
        --utilization-report "$ARTIFACT_ROOT/system_top_utilization_routed.rpt" \
        --timing-report "$ARTIFACT_ROOT/system_top_timing_summary_routed.rpt" \
        --route-status-report "$ARTIFACT_ROOT/system_top_route_status.rpt" \
        --drc-report "$ARTIFACT_ROOT/system_top_drc_routed.rpt" \
        --methodology-report "$ARTIFACT_ROOT/system_top_methodology_drc_routed.rpt" \
        --cdc-report "$ARTIFACT_ROOT/system_top_cdc_routed.rpt" \
        --bus-skew-report "$ARTIFACT_ROOT/system_top_bus_skew_routed.rpt" \
        --output "$integrated_verdict"
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
    payload_files=(
        "$(basename "$dfu")"
        "$(basename "$frm")"
        "$(basename "$xsa")"
        "$(basename "$rootfs")"
        "$(basename "$routed_dcp")"
        system_top.bit
        packed-fpga.bit
        system-top-bit.sha256
        frm-layout.txt
        system_top_timing_summary_routed.rpt
        system_top_route_status.rpt
        system_top_drc_routed.rpt
        system_top_methodology_drc_routed.rpt
        system_top_utilization_routed.rpt
        system_top_cdc_routed.rpt
        system_top_bus_skew_routed.rpt
        vivado-logs.tar.gz
    )
    if [[ -n "$INTEGRATED_WAIVERS" ]]; then
        payload_files+=("$(basename "$integrated_verdict")" "$(basename "$waiver_copy")")
    fi
    mapfile -t payload_files < <(
        printf '%s\n' "${payload_files[@]}" | LC_ALL=C sort
    )
    sha256sum "${payload_files[@]}" > PAYLOAD_SHA256SUMS
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
    if [[ -n "$INTEGRATED_WAIVERS" ]]; then
        echo '[integrated route verdict]'
        cat "$integrated_verdict"
    fi
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
    if [[ -n "$INTEGRATED_WAIVERS" ]]; then
        echo 'PASS fully routed design and complete timing/check_timing inventory'
        echo 'PASS exact reviewed DRC, methodology, CDC, and timestamp FIFO bus-skew inventories'
        echo 'PASS routed checkpoint, reports, waiver inventory, and integrated verdict retained by SHA-256'
    else
        echo 'PASS legacy routed timing, CDC-10, and timestamp FIFO bus-skew checks'
    fi
    echo 'PASS DFU suffix, FIT layout, XSA layout, and packaged-rootfs identity'
    echo 'PASS DFU FPGA payload is byte-identical to the qualified XSA bitstream'
    echo 'PASS persistent FRM trailer and exact DFU/FRM FIT-byte equivalence'
    echo 'PASS packaged ARM gadget binaries and mass-storage legal page'
    echo 'PASS final SHA-256 verification'
    echo
    echo 'This package has not accessed or been tested on radio hardware.'
    echo 'It must remain RAM-boot only until the hardware promotion gates pass.'
} > "$ARTIFACT_ROOT/offline-validation-summary.txt"

final_source_status="$(git status --porcelain --untracked-files=all)"
[[ "$final_source_status" == "$initial_source_status" ]] ||
    fail "source tree changed while packaging"
git status --short --branch > "$ARTIFACT_ROOT/git-status.txt"

mapfile -t checksum_files < <(
    cd "$ARTIFACT_ROOT"
    find . -maxdepth 1 -type f \
        ! -name SHA256SUMS \
        ! -name bundle-contents.txt \
        ! -name "$(basename "$bundle")" \
        ! -name "$(basename "$bundle").sha256" \
        -printf '%f\n' | LC_ALL=C sort
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
        -printf '%f\n' | LC_ALL=C sort)
    printf '%s\n' "${bundle_files[@]}" > bundle-contents.txt
    tar --sort=name --mtime="@${SOURCE_DATE_EPOCH:-0}" \
        --owner=0 --group=0 --numeric-owner \
        -cf - -T bundle-contents.txt | gzip -n > "$(basename "$bundle")"
    sha256sum "$(basename "$bundle")" > "$(basename "$bundle").sha256"
    sha256sum -c "$(basename "$bundle").sha256"
)

printf 'Deployment bundle: %s\n' "$bundle"
