from __future__ import annotations

from typing import Any

import pytest

from scripts.starlink_pss_m3_iio_tx_v2 import SingleTxCyclicIio, TxSafetyError
from tests.test_starlink_pss_m3_iio_tx_v1 import (
    FakeAttr,
    FakeChannel,
    FakeContext,
    FakeDevice,
    FakeIio,
)


class FreshWrapperDevice:
    """Model legacy pylibiio returning new wrappers for each channel view."""

    def __init__(self, channels: list[FakeChannel]) -> None:
        self._channels = channels

    @staticmethod
    def _clone(channel: FakeChannel) -> FakeChannel:
        return FakeChannel(
            channel.id,
            output=channel.output,
            index=channel.index,
            scan_element=channel.scan_element,
            enabled=channel.enabled,
            attrs=channel.attrs,
        )

    @property
    def channels(self) -> list[FakeChannel]:
        return [self._clone(channel) for channel in self._channels]

    def find_channel(self, name: str, output: bool) -> FakeChannel | None:
        return next(
            (
                self._clone(channel)
                for channel in self._channels
                if channel.id == name and channel.output is output
            ),
            None,
        )


def _channel(identifier: str, *, output: bool, gain: bool = False) -> FakeChannel:
    events: list[tuple[str, str]] = []
    attrs: dict[str, FakeAttr] = {}
    if gain:
        attrs.update(
            {
                "hardwaregain": FakeAttr(f"{identifier}-gain", -80, events),
                "sampling_frequency": FakeAttr("sample-rate", 30_720_000, events),
                "rf_bandwidth": FakeAttr("bandwidth", 18_000_000, events),
            }
        )
    if identifier == "altvoltage1":
        attrs.update(
            {
                "frequency": FakeAttr("lo", 2_400_000_000, events),
                "powerdown": FakeAttr("powerdown", 1, events),
            }
        )
    return FakeChannel(identifier, output=output, attrs=attrs)


def _context(phy: Any) -> FakeContext:
    tx = FakeDevice(
        [
            FakeChannel("voltage0", output=True, index=0, scan_element=True),
            FakeChannel("voltage1", output=True, index=1, scan_element=True),
        ]
    )
    return FakeContext("test-transmitter-0001", phy, tx)


def test_v2_accepts_distinct_legacy_wrappers_for_one_physical_gain_channel() -> None:
    phy = FreshWrapperDevice(
        [
            _channel("voltage0", output=False, gain=True),
            _channel("voltage0", output=True, gain=True),
            _channel("altvoltage1", output=True),
        ]
    )
    context = _context(phy)

    driver = SingleTxCyclicIio(
        FakeIio(), context, expected_serial="test-transmitter-0001"
    )

    assert context.timeout_ms == 5_000
    assert driver.phy_tx.id == "voltage0"
    assert driver.phy_tx.output is True


def test_v2_still_rejects_a_genuine_two_tx_gain_inventory() -> None:
    phy = FreshWrapperDevice(
        [
            _channel("voltage0", output=True, gain=True),
            _channel("voltage1", output=True, gain=True),
            _channel("altvoltage1", output=True),
        ]
    )

    with pytest.raises(TxSafetyError, match="exact single-TX"):
        SingleTxCyclicIio(
            FakeIio(), _context(phy), expected_serial="test-transmitter-0001"
        )
