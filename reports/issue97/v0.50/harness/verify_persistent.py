#!/usr/bin/env python3
"""Re-attest the final version, QSPI FIT, idle RX, and muted TX after reboot."""

import argparse
import json
from pathlib import Path

from maintain import ROOT, SERIAL, attest, link
from pluto_plus.bootstrap_firmware import (
    _REMOTE_RECONCILE_SCRIPT,
    PAIRED_RX_TX_CAPABLE_LAYOUT,
    SINGLE_RX_TX_CAPABLE_LAYOUT,
    _parse_reconciliation_report,
    _require_remote_tx_safe,
)
from pluto_plus.radio_lock import acquire_radio_lock

parser = argparse.ArgumentParser()
parser.add_argument("--paired", action="store_true")
args = parser.parse_args()
manifest = json.loads((ROOT.parent / "build/counter-rx-v1.json").read_text())
assert manifest["serial"] == SERIAL
with acquire_radio_lock(SERIAL):
    _, observed = attest()
    assert observed.firmware_version == manifest["firmware"]
    text = link().run(
        f"sh -s -- {SERIAL} {manifest['fit_size']}",
        stdin=_REMOTE_RECONCILE_SCRIPT,
        timeout_s=120,
    )
    fields = _parse_reconciliation_report(text)
    assert fields["serial"] == SERIAL and fields["firmware"] == manifest["firmware"]
    assert fields["fit_sha256"] == manifest["fit_sha256"]
    layout = PAIRED_RX_TX_CAPABLE_LAYOUT if args.paired else SINGLE_RX_TX_CAPABLE_LAYOUT
    _require_remote_tx_safe(fields, layout)
    initial = json.loads((ROOT / "persistent-result.json").read_text())
    receipt = json.loads(Path(initial["receipt_path"]).read_text())
    assert fields["boot_id"] != receipt["read_only_return_attestation"]["boot_id"]
    name = (
        "persistent-reboot-2r2t.json" if args.paired else "persistent-reboot-1r1t.json"
    )
    (ROOT / name).write_text(json.dumps(fields, indent=2) + "\n")
    print(json.dumps(fields, indent=2))
