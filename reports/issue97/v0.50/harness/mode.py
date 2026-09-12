#!/usr/bin/env python3
"""Change only the reviewed canonical mode tuple on the authorized radio."""

import argparse
import json

from maintain import ROOT, SERIAL, attest, link
from pluto_plus.bootstrap_firmware import mute_returned_radio_lan
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.setup_helper import SetupHelperError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["1r1t", "2r2t"])
    args = p.parse_args()
    with acquire_radio_lock(SERIAL):
        _, network = attest()
        assert network.firmware_version in (
            "v0.49-plutoplus-spf-iq-direct-async-v4",
            "v0.49-plutoplus-spf-counter-rx-v1-rc1",
            "v0.50-plutoplus-spf-counter-rx-v1",
        )
        transport = link()
        prefix = (
            'set -eu; test "$(cat /sys/kernel/config/usb_gadget/composite_gadget/strings/0x409/serialnumber)" = "'
            + SERIAL
            + '"; '
        )
        before = transport.run(
            prefix + "fw_printenv mode compatible attr_name attr_val", timeout_s=10
        )
        assert "compatible=ad9361" in before
        assert "attr_name=compatible" in before and "attr_val=ad9361" in before
        mute_returned_radio_lan(network.host, SERIAL)
        command = (
            prefix
            + "fw_setenv mode "
            + args.mode
            + '; test "$(fw_printenv -n mode)" = "'
            + args.mode
            + '"; sync; /usr/sbin/device_reboot reset'
        )
        (ROOT / ("mode-" + args.mode + "-transition.json")).write_text(
            json.dumps(
                {
                    "serial": SERIAL,
                    "before": before,
                    "requested_mode": args.mode,
                    "source_firmware": network.firmware_version,
                    "command": command,
                },
                indent=2,
            )
        )
        try:
            print(transport.run(command, timeout_s=15))
        except SetupHelperError as error:
            print(
                "Mode/reboot result is uncertain; attest the exact serial before continuing:",
                type(error).__name__,
            )


if __name__ == "__main__":
    main()
