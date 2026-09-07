"""Legacy-pylibiio-safe single-TX guard for the cabled M3 campaign.

The v1 implementation compared a channel returned by ``find_channel()`` with
the object yielded by ``device.channels``.  Legacy pylibiio creates distinct
Python wrappers for those two views even when both refer to the same physical
IIO channel.  This revision identifies the TX gain layout by stable channel
metadata while retaining every v1 mute, configuration, DMA, and cleanup
barrier.
"""

from __future__ import annotations

from typing import Any

import scripts.starlink_pss_m3_iio_tx_v1 as tx_v1

TxSafetyError = tx_v1.TxSafetyError
close_iio_context = tx_v1.close_iio_context
load_exact_payload = tx_v1.load_exact_payload


class SingleTxCyclicIio(tx_v1.SingleTxCyclicIio):
    """V1 transmitter lifecycle with stable single-TX layout attestation."""

    @staticmethod
    def _gain_key(channel: Any) -> tuple[str, bool]:
        return (
            str(getattr(channel, "id", "")),
            bool(getattr(channel, "output", False)),
        )

    def _attest_identity(self) -> None:
        attrs = {str(key): str(value) for key, value in self.context.attrs.items()}
        serial = attrs.get(
            "hw_serial", attrs.get("usb,serial", attrs.get("serial", ""))
        )
        if serial != self.expected_serial:
            raise TxSafetyError(
                f"IIO serial {serial!r} differs from {self.expected_serial!r}"
            )
        setter = getattr(self.context, "set_timeout", None)
        if not callable(setter):
            raise TxSafetyError("IIO context cannot set a bounded timeout")
        setter(5_000)

        selected_key = self._gain_key(self.phy_tx)
        selected_attrs = getattr(self.phy_tx, "attrs", {})
        gain_layout = tuple(
            self._gain_key(channel)
            for channel in self.phy.channels
            if bool(getattr(channel, "output", False))
            and "hardwaregain" in getattr(channel, "attrs", {})
        )
        if (
            selected_key != ("voltage0", True)
            or "hardwaregain" not in selected_attrs
            or gain_layout != (("voltage0", True),)
        ):
            raise TxSafetyError(
                "runtime is not an exact single-TX hardware-gain layout"
            )
        if "powerdown" not in getattr(self.tx_lo, "attrs", {}):
            raise TxSafetyError("TX LO lacks a powerdown control")
