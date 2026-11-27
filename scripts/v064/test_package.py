"""Exercise kernel replacement, protected FIT properties and rootfs identity."""
import gzip
import hashlib
import subprocess
import tempfile
import unittest
from collections import OrderedDict
from pathlib import Path

import package as pack


class PackagingTests(unittest.TestCase):
    def test_source_manifest_rejects_wrong_kernel_config_or_component_commit(self):
        manifest = {"submodule_linux": "a" * 40, "libiio_0_25_source": "b" * 40,
                    "kernel_zimage_sha256": pack.sha(b"kernel"),
                    "kernel_config_sha256": pack.sha(b"config")}
        pack.checked_manifest(manifest, "a" * 40, "b" * 40, b"kernel", b"config")
        for args in (("c" * 40, "b" * 40, b"kernel", b"config"),
                     ("a" * 40, "c" * 40, b"kernel", b"config"),
                     ("a" * 40, "b" * 40, b"wrong kernel", b"config"),
                     ("a" * 40, "b" * 40, b"kernel", b"wrong config")):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, "manifest mismatch"):
                pack.checked_manifest(manifest, *args)

    def fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = '''/dts-v1/;
            / { timestamp = <123>; images {
                linux_kernel@1 { data = [01 02]; compression = "none";
                    hash@1 { algo = "sha256"; value = [00]; }; };
                ramdisk@1 { data = [03 04]; compression = "gzip";
                    hash@1 { algo = "md5"; value = [00]; }; };
                fpga@1 { data = [05 06]; hash@1 { algo = "sha256"; value = [00]; }; };
            }; configurations { default = "config@0"; config@0 {
                kernel = "linux_kernel@1"; ramdisk = "ramdisk@1"; fpga = "fpga@1";
            }; }; };'''
            (directory / "test.dts").write_text(source)
            subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o",
                            str(directory / "test.dtb"), str(directory / "test.dts")], check=True)
            fit = pack.Fit((directory / "test.dtb").read_bytes())
            for path, props in fit.nodes().items():
                if path.count("/") == 3 and path.startswith("/images/"):
                    parent = path.rsplit("/", 1)[0]
                    algo = props["algo"].rstrip(b"\0").decode()
                    fit.replace(path, "value", hashlib.new(algo, fit.nodes()[parent]["data"]).digest())
            return fit.packed()

    def replacements(self):
        return {"/images/linux_kernel@1": b"new-kernel" * 1000, "/images/ramdisk@1": b"new-rootfs"}

    def test_kernel_rootfs_hashes_and_all_other_properties(self):
        original = self.fixture()
        output, unchanged = pack.replace_components(original, self.replacements())
        expected = pack.Fit(original).nodes()
        for path, payload in self.replacements().items():
            expected[path]["data"] = payload
            algo = expected[path + "/hash@1"]["algo"].rstrip(b"\0").decode()
            expected[path + "/hash@1"]["value"] = hashlib.new(algo, payload).digest()
        self.assertEqual(expected, pack.Fit(output).nodes())
        self.assertEqual(unchanged, {"/images/fpga@1": pack.sha(b"\x05\x06")})
        self.assertEqual(output, pack.replace_components(original, self.replacements())[0])

    def test_reject_corrupt_parent_kernel_and_fpga(self):
        for path in ("/images/linux_kernel@1", "/images/fpga@1"):
            with self.subTest(path=path):
                fit = pack.Fit(self.fixture())
                fit.replace(path, "data", b"corrupt")
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    pack.replace_components(fit.packed(), self.replacements())

    def test_reject_incomplete_inventory(self):
        with self.assertRaisesRegex(ValueError, "replacement inventory"):
            pack.replace_components(self.fixture(), {"/images/ramdisk@1": b"new"})

    def test_reject_missing_kernel_hash(self):
        fit = pack.Fit(self.fixture())
        fit.replace("/images/linux_kernel@1/hash@1", "algo", b"rsa2048\0")
        with self.assertRaisesRegex(ValueError, "unsupported FIT hash"):
            pack.replace_components(fit.packed(), self.replacements())

    def entries(self):
        entries = OrderedDict()
        versions = b"device-fw v0.63-plutoplus-spf-continuous-fast-scan\nlinux old\nlibiio old\nhdl retained\n"
        for index, (name, mode, payload) in enumerate((
                ("usr/sbin/iiod", 0o100755, b"old-daemon"),
                ("usr/lib/libiio.so.0.25", 0o100755, b"old-library"),
                ("usr/lib/libiio.so.0", 0o120777, b"libiio.so.0.25"),
                ("dev/console", 0o020600, b""),
                ("opt/VERSIONS", 0o100644, versions)), 1):
            entries[name] = ([index, mode, 4, 5, 1, 123, len(payload), 2, 3, 5, 1, len(name) + 1, 0], payload)
        return entries

    def test_rootfs_versions_and_metadata_roundtrip(self):
        original = self.entries()
        before = gzip.compress(pack.legacy.archive(original))
        replacement = {"usr/sbin/iiod": b"new-daemon", "usr/lib/libiio.so.0.25": b"new-library"}
        data, changes = pack.replace_rootfs(before, replacement, "a" * 40, "b" * 40)
        after = pack.legacy.cpio.read_newc(gzip.decompress(data))
        self.assertEqual(set(changes), set(replacement) | {"opt/VERSIONS"})
        self.assertEqual(list(after), list(original))
        for name, (metadata, payload) in after.items():
            self.assertEqual(metadata[:6] + metadata[7:], original[name][0][:6] + original[name][0][7:])
            if name not in changes:
                self.assertEqual(payload, original[name][1])
        self.assertIn(b"linux " + b"a" * 40, after["opt/VERSIONS"][1])
        self.assertIn(pack.VERSION.encode(), after["opt/VERSIONS"][1])
        self.assertEqual(data, pack.replace_rootfs(before, replacement, "a" * 40, "b" * 40)[0])

    def test_reject_wrong_parent_version(self):
        entries = self.entries()
        metadata, payload = entries["opt/VERSIONS"]
        entries["opt/VERSIONS"] = (metadata, payload.replace(b"v0.63", b"v0.62"))
        with self.assertRaisesRegex(ValueError, "parent version mismatch"):
            pack.replace_rootfs(gzip.compress(pack.legacy.archive(entries)),
                {"usr/sbin/iiod": b"new", "usr/lib/libiio.so.0.25": b"new"}, "a" * 40, "b" * 40)


if __name__ == "__main__":
    unittest.main()
