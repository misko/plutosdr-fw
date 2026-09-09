#!/usr/bin/env bash
# One bounded physical retry, preserving the failed source board byte-for-byte.
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo 'usage: retry_glrt_postroute.sh FAILED_BOARD NEW_OUTPUT_DIRECTORY' >&2
  exit 2
fi
repository=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_board=$(realpath "$1")
retry_output=$(realpath -m "$2")
if [[ -e "$retry_output" || "$retry_output" == "$source_board/"* ]]; then
  echo 'retry requires a new directory outside the source board' >&2
  exit 2
fi
test "$(cat "$source_board/build_exit_code.txt")" -eq 2
source_impl="$source_board/hdl/projects/pluto/pluto.runs/impl_1"
test -s "$source_impl/system_top_postroute_physopt.dcp"
test -s "$source_impl/system_top.bit"
mkdir -p "$retry_output"
trap 'printf "%s\n" "$?" > "$retry_output/build_exit_code.txt"' EXIT
sha256sum "$source_impl/system_top_postroute_physopt.dcp" "$source_impl/system_top.bit" \
  "$source_board/hdl/projects/pluto/pluto.xpr" \
  "$source_board/hdl/projects/pluto/system_constr.xdc" \
  "$source_board/hdl/library/axi_starlink_glrt/axi_starlink_glrt_constr.xdc" \
  > "$retry_output/original_inputs.sha256"
cp -a --reflink=auto "$source_board/hdl" "$retry_output/hdl"
cp "$source_board/hdl_commit.txt" "$source_board/source_rate_hz.txt" \
  "$source_board/firmware_parent_commit.txt" "$retry_output/"
printf '%s\n' "$source_board" > "$retry_output/original_board.txt"
sha256sum "$repository/scripts/retry_glrt_postroute.sh" \
  "$repository/scripts/retry_glrt_postroute.tcl" "$repository/scripts/report_glrt_board.tcl" \
  > "$retry_output/recipe.sha256"
retry_impl="$retry_output/hdl/projects/pluto/pluto.runs/impl_1"
mv "$retry_impl/system_top.bit" "$retry_output/original_system_top.bit"
cp "$retry_impl/system_top_postroute_physopt.dcp" "$retry_output/original_postroute.dcp"
set +u
source /opt/Xilinx/Vivado/2022.2/settings64.sh
set -u
export LD_LIBRARY_PATH="/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE:${LD_LIBRARY_PATH:-}"
export ADI_HDL_DIR="$retry_output/hdl"
if timeout --kill-after=30s 20m nice -n 10 vivado -mode batch \
  -source "$repository/scripts/retry_glrt_postroute.tcl" \
  -log "$retry_output/retry.log" -journal "$retry_output/retry.jou" \
  -tclargs "$retry_output/hdl/projects/pluto/pluto.xpr" "$retry_output" \
  > "$retry_output/retry-console.log" 2>&1; then
  retry_status=0
else
  retry_status=$?
fi
printf '%s\n' "$retry_status" > "$retry_output/optimization_exit_code.txt"
sha256sum --check "$retry_output/original_inputs.sha256" > "$retry_output/original_unchanged.log"
sha256sum --check "$retry_output/recipe.sha256" > "$retry_output/recipe_unchanged.log"
git -C "$retry_output/hdl" diff --exit-code > "$retry_output/source_validation.log"
if timeout --kill-after=30s 3m nice -n 10 vivado -mode batch \
  -source "$repository/scripts/report_glrt_board.tcl" \
  -log "$retry_output/full-audit.log" -journal "$retry_output/full-audit.jou" \
  -tclargs "$retry_output/hdl/projects/pluto/pluto.xpr" "$retry_output/full-audit" \
  > "$retry_output/full-audit-console.log" 2>&1; then
  audit_status=0
else
  audit_status=$?
fi
printf '%s\n' "$audit_status" > "$retry_output/audit_exit_code.txt"
sha256sum "$retry_impl/system_top_postroute_physopt.dcp" > "$retry_output/final_checkpoint.sha256"
test "$retry_status" -eq 0
test "$audit_status" -eq 0
test -s "$retry_output/hdl/projects/pluto/pluto.sdk/system_top.xsa"
test -s "$retry_impl/system_top.bit"
python3 - "$retry_output" <<'PY'
import hashlib, json, re, sys, zipfile
from pathlib import Path
root = Path(sys.argv[1])
lines = (root/'timing_after.rpt').read_text().splitlines()
row = next(lines[n+2].split() for n, line in enumerate(lines) if 'WNS(ns)' in line)
assert all(float(row[n]) >= 0 for n in (0, 4, 8)), row
assert all(int(row[n]) == 0 for n in (2, 6, 10)), row
routes = (root/'full-audit/route_status.rpt').read_text()
assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:', routes), routes
def clock_body(path):
    # Vivado sizes the banner rules from the command's output pathname.
    # Preserve every clock, waveform, uncertainty, jitter and device line.
    return '\n'.join(line for line in path.read_text().splitlines()
                     if not line.startswith(('| Date', '| Command'))
                     and not re.fullmatch(r'-+', line))
assert clock_body(root/'clocks_before.rpt') == clock_body(root/'clocks_after.rpt')
bit = root/'hdl/projects/pluto/pluto.runs/impl_1/system_top.bit'
xsa = root/'hdl/projects/pluto/pluto.sdk/system_top.xsa'
with zipfile.ZipFile(xsa) as archive:
    members = [name for name in archive.namelist() if name.endswith('.bit')]
    assert len(members) == 1 and archive.read(members[0]) == bit.read_bytes()
paths = [bit, xsa, root/'hdl/projects/pluto/pluto.runs/impl_1/system_top_postroute_physopt.dcp']
receipt = {'hdl_commit': (root/'hdl_commit.txt').read_text().strip(),
           'sequence': ['AlternateReplication', 'MoreGlobalIterations+tns_cleanup', 'AggressiveExplore'],
           'setup_slack_ns': float(row[0]), 'hold_slack_ns': float(row[4]),
           'pulse_slack_ns': float(row[8]), 'route_errors': 0,
           'effective_clocks_unchanged': True, 'xsa_contains_exact_final_bitstream': True,
           'sha256': {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
           'hardware_eligible': False, 'hardware_accessed': False}
(root/'retry_attestation.json').write_text(json.dumps(receipt, indent=2)+'\n')
PY
sha256sum "$retry_output/hdl/projects/pluto/pluto.sdk/system_top.xsa" \
  "$retry_impl/system_top.bit" > "$retry_output/outputs.sha256"
