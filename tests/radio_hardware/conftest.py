"""Explicit authorization and fail-safe fixtures for local radio tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

import pytest

from .experiment import Issue46Options, Issue46Radio
from .tandem_quality import (
    TandemQualityOptions,
    default_tx_trajectory,
    parse_tx_trajectory,
    validate_options,
)


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("plutosdr-fw radio hardware")
    group.addoption(
        "--issue46-hardware", action="store_true", help="run issue-46 RF tests"
    )
    group.addoption(
        "--tandem-quality-hardware",
        action="store_true",
        help="run the manual/native/tandem AGC TX2 quality matrix",
    )
    group.addoption(
        "--tx2-loopback", action="store_true", help="authorize attenuated TX2 RF"
    )
    group.addoption("--radio-serial", help="exact immutable radio serial")
    group.addoption(
        "--radio-uri", help="explicit IIO URI; USB is resolved by serial otherwise"
    )
    group.addoption(
        "--allow-non-usb",
        action="store_true",
        help="allow an explicitly supplied IP/local URI for transport comparison",
    )
    group.addoption("--firmware-pattern", help="required regex for context fw_version")
    group.addoption(
        "--libiio-source-commit",
        default=os.environ.get("PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT", ""),
        help="40-hex manifest-pinned host libiio source commit",
    )
    group.addoption("--loopback-attenuation-db", type=float)
    group.addoption("--tx2-gain-db", type=float, default=-20.0)
    group.addoption("--issue46-sample-rate", type=int, default=2_500_000)
    group.addoption("--issue46-samples", type=int, default=262_144)
    group.addoption("--issue46-profile", choices=("smoke", "repro"), default="repro")
    group.addoption("--issue46-sink", choices=("ram", "sync", "both"), default="ram")
    group.addoption(
        "--issue46-expected", choices=("red", "green", "either"), default="green"
    )
    group.addoption(
        "--issue46-output",
        type=Path,
        default=Path("build/radio-hardware/issue-46"),
    )
    group.addoption("--issue46-max-seconds", type=float, default=600.0)
    group.addoption("--issue46-save-iq", action="store_true")
    group.addoption("--pn-min-coherence", type=float, default=0.03)
    group.addoption("--pn-min-peak-ratio", type=float, default=1.5)
    group.addoption(
        "--tandem-quality-profile", choices=("smoke", "full"), default="smoke"
    )
    group.addoption(
        "--tandem-quality-tx-gains",
        help="comma-separated weak-to-strong-to-weak TX2 hardware gains in dB",
    )
    group.addoption("--tandem-quality-sample-rate", type=int, default=2_500_000)
    group.addoption("--tandem-quality-samples", type=int, default=65_536)
    group.addoption("--tandem-quality-dds-scale", type=float, default=1.0)
    group.addoption("--tandem-quality-manual-gain", type=float, default=40.0)
    group.addoption("--tandem-quality-low-power-threshold", type=int, default=20)
    group.addoption("--tandem-quality-large-lmt-threshold", type=int, default=58)
    group.addoption("--tandem-quality-large-adc-threshold", type=int, default=35)
    group.addoption("--tandem-quality-small-adc-threshold", type=int, default=34)
    group.addoption("--tandem-quality-measurements", type=int, default=3)
    group.addoption("--tandem-quality-stable-frames", type=int, default=3)
    group.addoption("--tandem-quality-max-settle-frames", type=int, default=64)
    group.addoption("--tandem-quality-settle-seconds", type=float, default=2.5)
    group.addoption("--tandem-quality-max-seconds", type=float, default=180.0)
    group.addoption(
        "--tandem-quality-output",
        type=Path,
        default=Path("build/radio-hardware/tandem-agc-quality"),
    )
    group.addoption("--tandem-quality-save-iq", action="store_true")


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    issue46_skip = pytest.mark.skip(
        reason="requires --issue46-hardware and explicit TX2 authorization"
    )
    quality_skip = pytest.mark.skip(
        reason="requires --tandem-quality-hardware and explicit TX2 authorization"
    )
    for item in items:
        if "issue46" in item.keywords and not config.getoption("--issue46-hardware"):
            item.add_marker(issue46_skip)
        if "tandem_quality" in item.keywords and not config.getoption(
            "--tandem-quality-hardware"
        ):
            item.add_marker(quality_skip)


@pytest.fixture(scope="session")
def issue46_options(pytestconfig: Any) -> Issue46Options:
    if not pytestconfig.getoption("--issue46-hardware"):
        pytest.skip("issue-46 hardware run was not requested")
    if not pytestconfig.getoption("--tx2-loopback"):
        pytest.fail("--tx2-loopback is required before any TX mutation", pytrace=False)
    serial = pytestconfig.getoption("--radio-serial")
    firmware_pattern = pytestconfig.getoption("--firmware-pattern")
    attenuation = pytestconfig.getoption("--loopback-attenuation-db")
    if not serial:
        pytest.fail("--radio-serial is required", pytrace=False)
    if not firmware_pattern:
        pytest.fail("--firmware-pattern is required", pytrace=False)
    if attenuation is None:
        pytest.fail("--loopback-attenuation-db is required", pytrace=False)
    return Issue46Options(
        serial=serial,
        uri=pytestconfig.getoption("--radio-uri"),
        allow_non_usb=pytestconfig.getoption("--allow-non-usb"),
        firmware_pattern=firmware_pattern,
        libiio_source_commit=pytestconfig.getoption("--libiio-source-commit"),
        attenuation_db=attenuation,
        tx_gain_db=pytestconfig.getoption("--tx2-gain-db"),
        sample_rate_hz=pytestconfig.getoption("--issue46-sample-rate"),
        samples_per_channel=pytestconfig.getoption("--issue46-samples"),
        profile=pytestconfig.getoption("--issue46-profile"),
        sink=pytestconfig.getoption("--issue46-sink"),
        expected=pytestconfig.getoption("--issue46-expected"),
        output_dir=pytestconfig.getoption("--issue46-output").resolve(),
        max_seconds=pytestconfig.getoption("--issue46-max-seconds"),
        save_iq=pytestconfig.getoption("--issue46-save-iq"),
        pn_min_coherence=pytestconfig.getoption("--pn-min-coherence"),
        pn_min_peak_ratio=pytestconfig.getoption("--pn-min-peak-ratio"),
    )


@pytest.fixture(scope="session")
def issue46_radio(issue46_options: Issue46Options) -> Iterator[Issue46Radio]:
    pytest.importorskip("numpy", reason="radio PN correlation requires numpy")
    try:
        import iio
    except ImportError:
        pytest.fail("manifest-pinned pylibiio is not importable", pytrace=False)
    radio = Issue46Radio(iio, issue46_options)
    try:
        yield radio
    finally:
        radio.close()


@pytest.fixture(scope="session")
def qualified_issue46_radio(issue46_radio: Issue46Radio) -> Issue46Radio:
    issue46_radio.qualify_tone()
    return issue46_radio


@pytest.fixture(scope="session")
def pnxx_issue46_radio(qualified_issue46_radio: Issue46Radio) -> Issue46Radio:
    qualified_issue46_radio.arm_pnxx()
    return qualified_issue46_radio


@pytest.fixture(scope="session")
def tandem_quality_options(pytestconfig: Any) -> TandemQualityOptions:
    if not pytestconfig.getoption("--tandem-quality-hardware"):
        pytest.skip("tandem AGC quality hardware run was not requested")
    if not pytestconfig.getoption("--tx2-loopback"):
        pytest.fail("--tx2-loopback is required before any TX mutation", pytrace=False)
    if not pytestconfig.getoption("--radio-serial"):
        pytest.fail("--radio-serial is required", pytrace=False)
    if not pytestconfig.getoption("--firmware-pattern"):
        pytest.fail("--firmware-pattern is required", pytrace=False)
    attenuation = pytestconfig.getoption("--loopback-attenuation-db")
    if attenuation is None:
        pytest.fail(
            "--loopback-attenuation-db must declare current physical loss",
            pytrace=False,
        )
    profile = pytestconfig.getoption("--tandem-quality-profile")
    supplied_levels = pytestconfig.getoption("--tandem-quality-tx-gains")
    try:
        levels = (
            parse_tx_trajectory(supplied_levels)
            if supplied_levels is not None
            else default_tx_trajectory(profile)
        )
        options = TandemQualityOptions(
            tx_gain_trajectory_db=levels,
            physical_attenuation_db=attenuation,
            sample_rate_hz=pytestconfig.getoption("--tandem-quality-sample-rate"),
            samples_per_channel=pytestconfig.getoption("--tandem-quality-samples"),
            dds_scale=pytestconfig.getoption("--tandem-quality-dds-scale"),
            manual_gain_db=pytestconfig.getoption("--tandem-quality-manual-gain"),
            tandem_low_power_threshold=pytestconfig.getoption(
                "--tandem-quality-low-power-threshold"
            ),
            tandem_large_lmt_overload_threshold=pytestconfig.getoption(
                "--tandem-quality-large-lmt-threshold"
            ),
            tandem_large_adc_overload_threshold=pytestconfig.getoption(
                "--tandem-quality-large-adc-threshold"
            ),
            tandem_small_adc_overload_threshold=pytestconfig.getoption(
                "--tandem-quality-small-adc-threshold"
            ),
            stable_frames=pytestconfig.getoption("--tandem-quality-stable-frames"),
            measurement_frames=pytestconfig.getoption("--tandem-quality-measurements"),
            max_settle_frames=pytestconfig.getoption(
                "--tandem-quality-max-settle-frames"
            ),
            settle_timeout_seconds=pytestconfig.getoption(
                "--tandem-quality-settle-seconds"
            ),
            max_seconds=pytestconfig.getoption("--tandem-quality-max-seconds"),
            output_dir=pytestconfig.getoption("--tandem-quality-output").resolve(),
            profile=profile,
            save_iq=pytestconfig.getoption("--tandem-quality-save-iq"),
        )
        validate_options(options)
    except ValueError as error:
        pytest.fail(str(error), pytrace=False)
    return options


@pytest.fixture(scope="session")
def tandem_quality_radio(
    pytestconfig: Any, tandem_quality_options: TandemQualityOptions
) -> Iterator[Issue46Radio]:
    pytest.importorskip("numpy", reason="tone-quality analysis requires numpy")
    try:
        import iio
    except ImportError:
        pytest.fail("manifest-pinned pylibiio is not importable", pytrace=False)
    radio_options = Issue46Options(
        serial=pytestconfig.getoption("--radio-serial"),
        uri=pytestconfig.getoption("--radio-uri"),
        allow_non_usb=pytestconfig.getoption("--allow-non-usb"),
        firmware_pattern=pytestconfig.getoption("--firmware-pattern"),
        libiio_source_commit=pytestconfig.getoption("--libiio-source-commit"),
        attenuation_db=tandem_quality_options.physical_attenuation_db,
        tx_gain_db=tandem_quality_options.strongest_tx_gain_db,
        sample_rate_hz=tandem_quality_options.sample_rate_hz,
        samples_per_channel=tandem_quality_options.samples_per_channel,
        profile="smoke",
        sink="ram",
        expected="green",
        output_dir=tandem_quality_options.output_dir,
        max_seconds=tandem_quality_options.max_seconds,
        save_iq=tandem_quality_options.save_iq,
        pn_min_coherence=0.03,
        pn_min_peak_ratio=1.5,
        lock_namespace="tandem-quality",
    )
    radio = Issue46Radio(iio, radio_options)
    try:
        yield radio
    finally:
        radio.close()
