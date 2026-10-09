"""Offline integrity tests for the scanner release packaging boundary."""
import gzip
import hashlib
import subprocess
import tempfile
import unittest
from collections import OrderedDict
from pathlib import Path

import package as pack
from fit import Fit


class PackagingTests(unittest.TestCase):
    def entries(self):
        result = OrderedDict()
        for i, (name, mode, payload) in enumerate((
            ("usr/sbin/iiod", 0o100755, b"old-daemon"),
            ("usr/lib/libiio.so.0.25", 0o100755, b"old-lib"),
            ("usr/lib/libiio.so.0", 0o120777, b"libiio.so.0.25"),
            ("dev/console", 0o020600, b""),
            ("opt/VERSIONS", 0o100644, b"device-fw v0.61-plutoplus-spf-fastlock-timeout-fix\nlinux preserved\nlibiio old\n"),
        ), 1):
            result[name] = ([i + 30, mode, 4, 5, 1, 123, len(payload), 2, 3, 5, 1, len(name) + 1, 0], payload)
        return result

    def test_rootfs_preserves_metadata_order_symlinks_devices(self):
        original = self.entries()
        base = gzip.compress(pack.archive(original))
        data, changes = pack.rootfs(base, {"usr/sbin/iiod": b"new-daemon", "usr/lib/libiio.so.0.25": b"new-lib"}, "a" * 40)
        result = pack.cpio.read_newc(gzip.decompress(data))
        self.assertEqual(list(original), list(result))
        self.assertEqual(set(changes), {"usr/sbin/iiod", "usr/lib/libiio.so.0.25", "opt/VERSIONS"})
        for name, (metadata, payload) in result.items():
            self.assertEqual(metadata[:6] + metadata[7:], original[name][0][:6] + original[name][0][7:])
            if name not in changes:
                self.assertEqual(payload, original[name][1])
        self.assertIn(b"linux preserved", result["opt/VERSIONS"][1])
        self.assertEqual(data, pack.rootfs(base, {"usr/sbin/iiod": b"new-daemon", "usr/lib/libiio.so.0.25": b"new-lib"}, "a" * 40)[0])

    def fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "test.dts").write_text('''/dts-v1/;
            / { timestamp = <123>; images {
                ramdisk@1 { data = [01 02]; compression = "gzip";
                    hash@1 { algo = "md5"; value = [00]; }; };
                fpga@1 { data = [03 04]; hash@1 { algo = "sha256"; value = [00]; }; };
            }; configurations { default = "config@0"; config@0 { ramdisk = "ramdisk@1"; fpga = "fpga@1"; }; }; };''')
            subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(p / "test.dtb"), str(p / "test.dts")], check=True)
            fit = Fit((p / "test.dtb").read_bytes())
            fit.replace("/images/ramdisk@1/hash@1", "value", hashlib.md5(b"\x01\x02").digest())
            fit.replace("/images/fpga@1/hash@1", "value", hashlib.sha256(b"\x03\x04").digest())
            return fit.packed()

    def test_fit_only_rootfs_and_hash_change(self):
        original = self.fixture()
        body, unchanged = pack.replace_ramdisk(original, b"replacement")
        before, after = Fit(original).nodes(), Fit(body).nodes()
        before["/images/ramdisk@1"]["data"] = b"replacement"
        before["/images/ramdisk@1/hash@1"]["value"] = hashlib.md5(b"replacement").digest()
        self.assertEqual(before, after)
        self.assertEqual(set(unchanged), {"/images/fpga@1"})
        self.assertEqual(body, pack.replace_ramdisk(original, b"replacement")[0])

    def test_reject_corrupt_original_component(self):
        fit = Fit(self.fixture())
        fit.replace("/images/fpga@1", "data", b"corrupt")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            pack.replace_ramdisk(fit.packed(), b"new")

    def test_reject_signed_fit(self):
        fit = Fit(self.fixture())
        # The signed-property policy is intentionally conservative.
        fit.replace("/images/ramdisk@1/hash@1", "algo", b"rsa2048\0")
        with self.assertRaisesRegex(ValueError, "unsupported FIT hash"):
            pack.replace_ramdisk(fit.packed(), b"new")

    def test_dfu_crc_corruption_rejected(self):
        body = self.fixture()
        dfu = pack.cpio.add_dfu_suffix(body)
        self.assertEqual(pack.cpio.fit_body(dfu), body)
        with self.assertRaisesRegex(pack.cpio.CandidateError, "CRC"):
            pack.cpio.fit_body(dfu[:-1] + bytes([dfu[-1] ^ 1]))

    def test_unexpected_payload_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexpected executable inventory"):
            pack.rootfs(gzip.compress(pack.archive(self.entries())), {"dev/console": b"bad"}, "a" * 40)


if __name__ == "__main__":
    unittest.main()
