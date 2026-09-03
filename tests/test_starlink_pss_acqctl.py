from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/starlink_pssctl"
MMIO_BASE = 0x79040000
MMIO_SPAN = 0x1000

REG_IDENTIFICATION = 0x00
REG_VERSION = 0x04
REG_PHASE_BINS = 0x08
REG_TILE_GEOMETRY = 0x0C
REG_CAPABILITIES = 0x10
REG_CONTROL = 0x14
REG_STATUS = 0x18
REG_INPUT_RATE_MSPS = 0xB0
REG_DDC_CONFIG = 0xB4
REG_DDC_GROUP_DELAY = 0xB8
REG_COEFFICIENT_ENERGY = 0xBC
REG_DDC_CONTRACT_0 = 0xC0

SERIAL = "104000bac4950008230026001b440a003a"
CONTRACT_30 = (
    0x73142604,
    0x7077B036,
    0xF9213DB3,
    0x574E4A55,
    0x6FD424B9,
    0x7A293843,
    0xBD6EE085,
    0xC2BF33AF,
)


def _write32(path: Path, offset: int, value: int) -> None:
    with path.open("r+b") as output:
        output.seek(MMIO_BASE + offset)
        output.write(struct.pack("<I", value))


def _read32(path: Path, offset: int) -> int:
    with path.open("rb") as source:
        source.seek(MMIO_BASE + offset)
        return struct.unpack("<I", source.read(4))[0]


@pytest.fixture()
def acqctl_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    serial_file = tmp_path / "serial"
    serial_file.write_text(SERIAL + "\n", encoding="ascii")
    devmem = tmp_path / "devmem"
    with devmem.open("wb") as output:
        output.truncate(MMIO_BASE + MMIO_SPAN)

    values = {
        REG_IDENTIFICATION: 0x50534D41,
        REG_VERSION: 0x00010002,
        REG_PHASE_BINS: 20_000,
        REG_TILE_GEOMETRY: 0x00401002,
        REG_CAPABILITIES: 0x0000007F,
        REG_STATUS: 0x00000001,
        REG_INPUT_RATE_MSPS: 30,
        REG_DDC_CONFIG: 0x000F0203,
        REG_DDC_GROUP_DELAY: 7,
        REG_COEFFICIENT_ENERGY: 1_073_744_004,
    }
    for offset, value in values.items():
        _write32(devmem, offset, value)
    for index, value in enumerate(CONTRACT_30):
        _write32(devmem, REG_DDC_CONTRACT_0 + 4 * index, value)

    binary = tmp_path / "starlink_pss_acqctl"
    subprocess.run(
        [
            "cc",
            "-O2",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wpedantic",
            f'-DSTARLINK_PSS_SERIAL_FILE="{serial_file}"',
            str(SOURCE / "starlink_pss_acquisition.c"),
            str(SOURCE / "starlink_pss_acqctl.c"),
            "-lm",
            "-o",
            str(binary),
        ],
        check=True,
    )
    return binary, devmem, serial_file


def test_info_validates_serial_mmio_and_rate_contract(
    acqctl_fixture: tuple[Path, Path, Path],
) -> None:
    binary, devmem, _ = acqctl_fixture
    completed = subprocess.run(
        [
            str(binary),
            "--expect-serial",
            SERIAL,
            "--devmem",
            str(devmem),
            "info",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    report = json.loads(completed.stdout)

    assert report["schema"] == "starlink-pss-acqctl.info.v1"
    assert report["claim_scope"] == "hardware_contract_only"
    assert report["serial"] == SERIAL
    assert report["mmio_base"] == "0x79040000"
    assert report["abi_version"] == "0x00010002"
    assert report["input_rate_msps"] == 30
    assert report["canonical_rate_msps"] == 15
    assert report["decimation_factor"] == 2
    assert report["ddc_contract_words"] == [f"0x{value:08x}" for value in CONTRACT_30]


def test_serial_mismatch_fails_before_devmem_open(
    acqctl_fixture: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    binary, _, _ = acqctl_fixture
    completed = subprocess.run(
        [
            str(binary),
            "--expect-serial",
            "0" * len(SERIAL),
            "--devmem",
            str(tmp_path / "does-not-exist"),
            "info",
        ],
        check=False,
        text=True,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode != 0
    assert "radio serial mismatch" in completed.stderr
    assert "cannot open" not in completed.stderr


def test_candidate_timeout_still_disables_and_flushes(
    acqctl_fixture: tuple[Path, Path, Path],
) -> None:
    binary, devmem, _ = acqctl_fixture
    completed = subprocess.run(
        [
            str(binary),
            "--expect-serial",
            SERIAL,
            "--devmem",
            str(devmem),
            "candidate",
            "--timeout-ms",
            "1",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "timed out" in completed.stderr
    assert _read32(devmem, REG_CONTROL) == 2
