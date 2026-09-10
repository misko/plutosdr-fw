"""Small libiio 0.x binding for strict GLR1 scans; importing opens no devices."""
from __future__ import annotations

import ctypes as C
import ctypes.util
import os


class DataFormat(C.Structure):
    _fields_ = [("length", C.c_uint), ("bits", C.c_uint), ("shift", C.c_uint),
                ("is_signed", C.c_bool), ("is_fully_defined", C.c_bool),
                ("is_be", C.c_bool), ("with_scale", C.c_bool),
                ("scale", C.c_double), ("repeat", C.c_uint)]


def checked(value: int, operation: str) -> int:
    if value < 0:
        raise OSError(-value, f"{operation}: {os.strerror(-value)}")
    return value


class Library:
    def __init__(self, path=None):
        self.path = path or ctypes.util.find_library("iio")
        if not self.path:
            raise OSError("libiio 0.x is unavailable")
        self.lib = C.CDLL(self.path, use_errno=True)
        ptr, string, size, signed = C.c_void_p, C.c_char_p, C.c_size_t, C.c_ssize_t
        declarations = {
            "library_get_version": (None, C.POINTER(C.c_uint), C.POINTER(C.c_uint), ptr),
            "create_context_from_uri": (ptr, string),
            "context_destroy": (None, ptr), "context_set_timeout": (C.c_int, ptr, C.c_uint),
            "context_get_attrs_count": (C.c_uint, ptr),
            "context_get_attr": (C.c_int, ptr, C.c_uint, C.POINTER(string), C.POINTER(string)),
            "context_find_device": (ptr, ptr, string),
            "device_get_channels_count": (C.c_uint, ptr),
            "device_get_channel": (ptr, ptr, C.c_uint),
            "device_find_channel": (ptr, ptr, string, C.c_bool),
            "device_get_sample_size": (signed, ptr),
            "device_set_kernel_buffers_count": (C.c_int, ptr, C.c_uint),
            "device_create_buffer": (ptr, ptr, size, C.c_bool),
            "device_attr_read": (signed, ptr, string, ptr, size),
            "device_attr_write": (signed, ptr, string, string),
            "channel_attr_read": (signed, ptr, string, ptr, size),
            "channel_attr_write": (signed, ptr, string, string),
            "channel_get_id": (string, ptr), "channel_get_index": (C.c_long, ptr),
            "channel_is_output": (C.c_bool, ptr), "channel_is_scan_element": (C.c_bool, ptr),
            "channel_get_data_format": (C.POINTER(DataFormat), ptr),
            "channel_enable": (None, ptr), "channel_disable": (None, ptr),
            "buffer_refill": (signed, ptr), "buffer_start": (ptr, ptr),
            "buffer_end": (ptr, ptr), "buffer_step": (signed, ptr),
            "buffer_cancel": (None, ptr), "buffer_destroy": (None, ptr),
        }
        for name, (result, *arguments) in declarations.items():
            function = getattr(self.lib, "iio_" + name)
            function.restype, function.argtypes = result, arguments
            setattr(self, name, function)
        major, minor, tag = C.c_uint(), C.c_uint(), C.create_string_buffer(8)
        self.library_get_version(C.byref(major), C.byref(minor), tag)
        if major.value != 0 or minor.value < 21:
            raise ValueError("GLR1 collector requires libiio 0.x, version 0.21 or newer")
        self.version = f"{major.value}.{minor.value}-{tag.value.decode()}"

    def pointer(self, value, operation):
        if not value:
            error = C.get_errno() or 5
            raise OSError(error, f"{operation}: {os.strerror(error)}")
        return value


class Context:
    def __init__(self, library, uri, serial, firmware, timeout_ms=10_000):
        self.api, self.pointer, self.buffers = library, None, []
        self.pointer = library.pointer(library.create_context_from_uri(uri.encode()), "open IIO context")
        try:
            self.timeout(timeout_ms)
            self.attributes = {}
            for index in range(library.context_get_attrs_count(self.pointer)):
                name, value = C.c_char_p(), C.c_char_p()
                checked(library.context_get_attr(self.pointer, index, C.byref(name), C.byref(value)),
                        "read IIO context attribute")
                self.attributes[name.value.decode()] = value.value.decode()
            if self.attributes.get("hw_serial") != serial:
                raise ValueError("IIO hardware serial differs from the requested receiver")
            if self.attributes.get("fw_version") != firmware:
                raise ValueError("IIO firmware version differs from the requested build")
        except BaseException:
            self.close()
            raise

    def timeout(self, milliseconds):
        checked(self.api.context_set_timeout(self.pointer, milliseconds), "set IIO timeout")

    def device(self, name):
        pointer = self.api.context_find_device(self.pointer, name.encode())
        if not pointer:
            raise ValueError(f"required IIO device is missing: {name}")
        return Device(self, pointer)

    def close(self):
        if self.buffers:
            raise RuntimeError("close/cancel and join buffer consumers before closing their IIO context")
        if self.pointer:
            self.api.context_destroy(self.pointer)
            self.pointer = None


class Attributes:
    def read(self, name):
        buf = C.create_string_buffer(4096)
        length = checked(self._read(self.pointer, name.encode(), buf, len(buf)), f"read {name}")
        if length >= len(buf):
            raise ValueError(f"truncated IIO attribute: {name}")
        return buf.raw[:length].rstrip(b"\0\n").decode()

    def write(self, name, value):
        checked(self._write(self.pointer, name.encode(), str(value).encode()), f"write {name}")
        if self.read(name) != str(value):
            raise ValueError(f"IIO attribute readback differs: {name}")


class Channel(Attributes):
    def __init__(self, context, pointer):
        self.context, self.api, self.pointer = context, context.api, pointer
        self._read, self._write = self.api.channel_attr_read, self.api.channel_attr_write


class Device(Attributes):
    def __init__(self, context, pointer):
        self.context, self.api, self.pointer = context, context.api, pointer
        self._read, self._write = self.api.device_attr_read, self.api.device_attr_write

    def command(self, name, value):
        """Write an acknowledged command attribute that has no readback value.

        Configuration still uses write() and its equality readback. Command
        callers must inspect the command's documented result/status interface.
        """
        checked(self._write(self.pointer, name.encode(), str(value).encode()), f"command {name}")

    def channel(self, name, output=False):
        pointer = self.api.device_find_channel(self.pointer, name.encode(), output)
        if not pointer:
            raise ValueError(f"required IIO channel is missing: {name}")
        return Channel(self.context, pointer)

    def scan(self, *, count, bits, signed):
        found = []
        for number in range(self.api.device_get_channels_count(self.pointer)):
            channel = self.api.device_get_channel(self.pointer, number)
            if not self.api.channel_is_scan_element(channel):
                continue
            self.api.channel_disable(channel)
            fmt = self.api.channel_get_data_format(channel).contents
            if (self.api.channel_is_output(channel) or fmt.length != bits or fmt.bits != bits
                    or fmt.shift != 0 or fmt.is_signed != signed or fmt.is_be
                    or fmt.with_scale or fmt.repeat != 1):
                raise ValueError("IIO scan does not have the exact GLR1 wire format")
            found.append((self.api.channel_get_index(channel), channel))
        if sorted(index for index, _ in found) != list(range(count)):
            raise ValueError("IIO scan has missing, additional or reordered GLR1 channels")
        for _, channel in found:
            self.api.channel_enable(channel)
        self.stride = count * bits // 8
        if self.api.device_get_sample_size(self.pointer) != self.stride:
            raise ValueError("IIO scan size differs from GLR1 wire size")

    def buffer(self, samples, kernel_buffers):
        checked(self.api.device_set_kernel_buffers_count(self.pointer, kernel_buffers),
                "configure IIO kernel buffer count")
        return Buffer(self, samples)


class Buffer:
    def __init__(self, device, samples):
        self.device, self.api, self.samples = device, device.api, samples
        self.pointer = self.api.pointer(self.api.device_create_buffer(device.pointer, samples, False),
                                        "create IIO buffer")
        device.context.buffers.append(self)

    def refill(self):
        length = checked(self.api.buffer_refill(self.pointer), "refill IIO buffer")
        start, end = self.api.buffer_start(self.pointer), self.api.buffer_end(self.pointer)
        if (not start or not end or end-start < length or length <= 0
                or length > self.samples*self.device.stride or length % self.device.stride
                or self.api.buffer_step(self.pointer) != self.device.stride):
            raise ValueError("IIO returned an invalid GLR1 buffer extent or scan stride")
        return C.string_at(start, length)

    def cancel(self):
        if self.pointer:
            self.api.buffer_cancel(self.pointer)

    def close(self):
        if self.pointer:
            self.api.buffer_destroy(self.pointer)
            self.pointer = None
            self.device.context.buffers.remove(self)
