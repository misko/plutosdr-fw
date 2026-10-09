"""Minimal libfdt adapter for preserving component-replacement FIT properties."""
import ctypes
import ctypes.util
import struct

class Fit:
    """Bounded libfdt adapter: preserve every property outside explicit updates."""

    def __init__(self, data: bytes, capacity: int | None = None):
        if len(data) < 40 or data[:4] != b"\xd0\x0d\xfe\xed":
            raise ValueError("missing FIT/FDT header")
        total = struct.unpack_from(">I", data, 4)[0]
        if not 40 <= total <= min(len(data), 64 * 1024 * 1024):
            raise ValueError("FIT size is truncated or exceeds bound")
        self.original = data[:total]  # QSPI partition padding is excluded.
        library = ctypes.util.find_library("fdt")
        if library is None:
            raise RuntimeError("libfdt is required (device-tree-compiler package)")
        self.lib = ctypes.CDLL(library)
        signatures = {
            "fdt_check_full": ([ctypes.c_void_p, ctypes.c_size_t], ctypes.c_int),
            "fdt_open_into": ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            "fdt_next_node": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)],
                ctypes.c_int,
            ),
            "fdt_get_path": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int],
                ctypes.c_int,
            ),
            "fdt_first_property_offset": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            "fdt_next_property_offset": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            "fdt_get_property_by_offset": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)],
                ctypes.c_void_p,
            ),
            "fdt_string": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_char_p),
            "fdt_path_offset": ([ctypes.c_void_p, ctypes.c_char_p], ctypes.c_int),
            "fdt_setprop": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int],
                ctypes.c_int,
            ),
            "fdt_pack": ([ctypes.c_void_p], ctypes.c_int),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes = arguments
            function.restype = result
        source = ctypes.create_string_buffer(self.original)
        self.check(self.lib.fdt_check_full(source, total))
        self.buffer = ctypes.create_string_buffer(capacity or total + 4096)
        self.check(self.lib.fdt_open_into(source, self.buffer, len(self.buffer)))

    @staticmethod
    def check(result: int) -> None:
        if result < 0:
            raise ValueError(f"libfdt rejected FIT: {result}")

    def nodes(self) -> dict[str, dict[str, bytes]]:
        result = {}
        depth = ctypes.c_int(0)
        offset = -1
        while True:
            offset = self.lib.fdt_next_node(self.buffer, offset, ctypes.byref(depth))
            if offset == -1 or depth.value < 0:
                break
            self.check(offset)
            path_buffer = ctypes.create_string_buffer(4096)
            self.check(self.lib.fdt_get_path(self.buffer, offset, path_buffer, 4096))
            path = path_buffer.value.decode("ascii")
            if path in result or len(result) >= 4096 or depth.value > 32:
                raise ValueError("duplicate/excessive FIT nodes")
            properties = {}
            prop = self.lib.fdt_first_property_offset(self.buffer, offset)
            while prop != -1:
                self.check(prop)
                size = ctypes.c_int()
                address = self.lib.fdt_get_property_by_offset(self.buffer, prop, ctypes.byref(size))
                if not address or size.value < 0:
                    raise ValueError("invalid FIT property")
                _, length, name_offset = struct.unpack(">III", ctypes.string_at(address, 12))
                name = self.lib.fdt_string(self.buffer, name_offset).decode("ascii")
                if name in properties or length != size.value:
                    raise ValueError("duplicate FIT property or length mismatch")
                properties[name] = ctypes.string_at(address + 12, length)
                prop = self.lib.fdt_next_property_offset(self.buffer, prop)
            result[path] = properties
        return result

    def replace(self, path: str, name: str, value: bytes) -> None:
        offset = self.lib.fdt_path_offset(self.buffer, path.encode("ascii"))
        self.check(offset)
        data = ctypes.create_string_buffer(value)
        self.check(
            self.lib.fdt_setprop(self.buffer, offset, name.encode("ascii"), data, len(value))
        )

    def packed(self) -> bytes:
        self.check(self.lib.fdt_pack(self.buffer))
        total = struct.unpack_from(">I", self.buffer.raw, 4)[0]
        result = self.buffer.raw[:total]
        self.check(self.lib.fdt_check_full(self.buffer, total))
        return result
