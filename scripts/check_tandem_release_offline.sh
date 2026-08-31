#!/usr/bin/env bash
# Reproduce the hardware-free tandem release checks used by pull requests.

set -euo pipefail
umask 0022

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
MODE="${1:-all}"

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

[[ $# -le 1 ]] || fail "usage: $0 [all|oracles|source-graph]"
case "$MODE" in
all | oracles | source-graph) ;;
*) fail "unknown offline-check mode: $MODE" ;;
esac

cd "$ROOT"

run_oracles() {
    command -v "$PYTHON" >/dev/null || fail "Python not found: $PYTHON"
    command -v iverilog >/dev/null || fail "iverilog is required for RTL oracles"

    bash -n \
        download_and_test.sh \
        scripts/build_gain_series_candidate.sh \
        scripts/ci/package_main_firmware.sh \
        scripts/deploy_tandem_agc_ram_hardware.sh \
        scripts/run_muted_metadata_batch_lifecycle_hardware.sh \
        scripts/run_stale_small_adc_hardware.sh \
        scripts/run_tandem_agc_ooc.sh \
        scripts/run_tandem_agc_release_hardware.sh \
        scripts/verify_release.sh

    "$PYTHON" -m pytest \
        tests/test_release_oracles.py \
        tests/test_firmware_release_tooling.py \
        tests/test_tandem_rc5_release_route.py \
        tests/test_tandem_rc6_release_route.py \
        tests/test_tandem_rc7_release_route.py \
        tests/test_tandem_rc8_release_route.py \
        tests/test_tandem_rc9_release_route.py \
        tests/test_tandem_rc10_release_route.py \
        tests/test_tandem_rc11_release_route.py \
        tests/test_tandem_rc12_release_route.py \
        tests/test_tandem_rc13_release_route.py \
        tests/test_tandem_rc14_release_route.py \
        tests/test_tandem_rc15_release_route.py \
        tests/test_tandem_rc16_release_route.py \
        tests/test_tandem_rc17_release_route.py \
        tests/test_tandem_rc18_release_route.py \
        tests/test_tandem_rc19_release_route.py \
        tests/test_tandem_rc20_release_route.py \
        tests/test_tandem_rc21_release_route.py \
        tests/test_tandem_rc22_release_route.py \
        tests/test_tandem_rc23_release_route.py \
        tests/test_tandem_rc24_release_route.py \
        tests/test_tandem_rc25_release_route.py \
        tests/test_tandem_rc26_release_route.py \
        tests/test_tandem_rc27_release_route.py \
        tests/test_tandem_rc28_release_route.py \
        tests/test_tandem_rc29_release_route.py \
        tests/test_tandem_rc30_release_route.py \
        tests/test_tandem_rc31_release_route.py \
        tests/test_tandem_rc32_release_route.py \
        tests/test_tandem_release_device_plan.py \
        tests/test_tandem_release_evidence.py \
        tests/test_tandem_agc_ooc_validator.py \
        tests/test_validate_integrated_release.py \
        tests/radio_hardware \
        -m 'not radio_hardware'

    ./hdl-tandem/run_tests.sh
    git diff --check
}

run_source_graph() {
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc3-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc4-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc5-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc6-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc7-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc8-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc9-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc10-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc11-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc12-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc13-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc14-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc15-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc16-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc17-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc18-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc19-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc20-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc21-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc22-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc23-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc24-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc25-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc26-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc27-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc28-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc29-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc30-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc31-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-rc32-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/tandem-agc-v8-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/metadata-timeout-main-v1-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/single-rx-metadata-rc1-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-burst-v1-rc1-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-burst-v1-rc2-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-burst-v1-rc3-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-burst-v1-rc4-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-burst-v1-rc5-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-burst-v2-rc1-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-burst-v2-rc2-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-burst-v2-rc3-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-capacity-test-rc1-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-ring-v1-rc1-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-ring-v1-rc2-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/ddr-ring-prefill-v1-rc1-source.yaml
    ./scripts/check_source_graph.sh manifests/iq-direct-async-ring-v1-rc1-source.yaml
    ./scripts/check_source_graph.sh manifests/iq-direct-async-v2-source.yaml
    SOURCE_GRAPH_CHECK_WORKTREE=0 ./scripts/check_source_graph.sh manifests/iio-throughput-coverage-window-v6-rc1-source.yaml
    ./buildroot/board/pluto/test_iiod_supervisor.sh
    ./scripts/test_legal_info_network.sh
}

case "$MODE" in
all)
    run_oracles
    run_source_graph
    ;;
oracles) run_oracles ;;
source-graph) run_source_graph ;;
esac

printf 'PASS: tandem release offline checks (%s)\n' "$MODE"
