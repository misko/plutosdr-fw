#!/usr/bin/env python3
"""SSH over a socket bound to the sole serial-attested USB interface."""

import argparse
import ctypes
import json
import socket
from pathlib import Path

import paramiko
from maintain import ROOT, SERIAL, password


def connect():
    ctypes.CDLL(
        "/home/mouse9911/gits/pluto-plus-utils-issue-97/.venv/lib/libiio.so.0",
        mode=ctypes.RTLD_GLOBAL,
    )
    import iio
    from pluto_plus.inventory import scan_local_usb_plutos

    selected = [d for d in scan_local_usb_plutos() if d.serial == SERIAL]
    assert len(selected) == 1
    device = selected[0]
    context = iio.Context(f"usb:{device.bus_number}.{device.device_number}.5")
    assert context.attrs["hw_serial"] == SERIAL
    assert context.attrs["fw_version"].startswith("v0.49-plutoplus-spf-")
    assert len(device.host_network_interfaces) == 1
    interface = device.host_network_interfaces[0].name
    sock = socket.socket()
    sock.setsockopt(
        socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b"\0"
    )
    sock.settimeout(10)
    sock.connect(("192.168.2.1", 22))
    transport = paramiko.Transport(sock)
    transport.start_client(timeout=10)
    key = transport.get_remote_server_key()
    # This enrollment is bound to the exact physical USB path attested above.
    # Retain the key and boot identity; never enroll through an ambiguous route.
    identity = {
        "serial": SERIAL,
        "usb_path": device.usb_path,
        "interface": interface,
        "firmware": context.attrs["fw_version"],
        "key_type": key.get_name(),
        "key": key.get_base64(),
    }
    (ROOT / "usb-ssh-identity.json").write_text(json.dumps(identity, indent=2))
    transport.auth_password("root", password())
    chan = transport.open_session()
    chan.exec_command(
        "cat /sys/kernel/config/usb_gadget/composite_gadget/strings/0x409/serialnumber"
    )
    assert chan.makefile("rb").read().decode().strip() == SERIAL
    assert chan.recv_exit_status() == 0
    return transport


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command_file", type=Path)
    args = p.parse_args()
    transport = connect()
    try:
        channel = transport.open_session()
        channel.exec_command(args.command_file.read_text())
        print(channel.makefile("rb").read().decode(), end="")
        print(channel.makefile_stderr("rb").read().decode(), end="")
        raise SystemExit(channel.recv_exit_status())
    finally:
        transport.close()


if __name__ == "__main__":
    main()
