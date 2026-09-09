"""C binding identity and byte-extent checks without any libiio context."""
import ctypes as C
from types import SimpleNamespace

import pytest

from tools.starlink_glrt_iio import Buffer, Context


class IdentityLibrary:
    def __init__(self, serial, firmware):
        self.attributes = [(b"hw_serial", serial.encode()), (b"fw_version", firmware.encode())]
        self.destroyed = []

    def create_context_from_uri(self, uri):
        assert uri == b"fake:identity"
        return 7

    def pointer(self, value, operation):
        return value

    def context_set_timeout(self, pointer, value):
        return 0

    def context_get_attrs_count(self, pointer):
        return len(self.attributes)

    def context_get_attr(self, pointer, index, name, value):
        name._obj.value, value._obj.value = self.attributes[index]
        return 0

    def context_destroy(self, pointer):
        self.destroyed.append(pointer)


@pytest.mark.parametrize("serial,firmware", [("wrong", "fw"), ("serial", "wrong")])
def test_wrong_receiver_or_firmware_closes_context_before_any_device_access(serial, firmware):
    api = IdentityLibrary(serial, firmware)
    with pytest.raises(ValueError):
        Context(api, "fake:identity", "serial", "fw")
    assert api.destroyed == [7]


def test_context_cannot_be_destroyed_while_a_buffer_is_live():
    api = IdentityLibrary("serial", "fw")
    context = Context(api, "fake:identity", "serial", "fw")
    context.buffers.append(object())
    with pytest.raises(RuntimeError):
        context.close()
    assert not api.destroyed
    context.buffers.clear()
    context.close()
    context.close()
    assert api.destroyed == [7]


def buffer(length, extent=8, step=4):
    raw = C.create_string_buffer(b"12345678")
    base = C.addressof(raw)
    result = Buffer.__new__(Buffer)
    result.device = SimpleNamespace(stride=4)
    result.samples, result.pointer = 2, 7
    result.api = SimpleNamespace(buffer_refill=lambda p: length, buffer_start=lambda p: base,
                                 buffer_end=lambda p: base+extent, buffer_step=lambda p: step,
                                 keepalive=raw)
    return result


@pytest.mark.parametrize("length,extent,step", [(0, 8, 4), (12, 12, 4), (8, 4, 4),
                                             (7, 8, 4), (8, 8, 8)])
def test_invalid_refill_extent_rejected_before_copy(length, extent, step):
    with pytest.raises(ValueError):
        buffer(length, extent, step).refill()


def test_refill_uses_actual_byte_count_and_preserves_errno():
    assert buffer(4).refill() == b"1234"
    assert buffer(8).refill() == b"12345678"
    with pytest.raises(OSError) as error:
        buffer(-110).refill()
    assert error.value.errno == 110
