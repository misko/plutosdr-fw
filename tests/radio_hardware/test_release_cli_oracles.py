"""Hardware-free parser, planning, resume, and aggregate-verdict oracles."""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from . import release_cli as release_cli_module
from .candidate_binding import REQUIRED_EVIDENCE_ROLES
from .metadata_abi import (
    TandemEventDirection,
    TandemGainEvent,
    parse_tandem_frame_metadata,
)
from .modulated_hardware import (
    DEFAULT_MODULATED_TX2_GAIN_DB,
    MODE_NATIVE_HYBRID,
    MODE_TANDEM,
    RELEASE_MODULATED_MODES,
    ModulatedHardwareOptions,
    evaluate_modulated_hardware_report,
    modulated_mode_evidence_policy,
)
from .pluto_plus_candidate_test_support import build_utility_deployment_bundle
from .release_campaign import build_release_plan
from .release_cli import (
    AGGREGATE_CHECKPOINT,
    DIAGNOSTIC_BAND,
    DIAGNOSTIC_FAIL,
    DIAGNOSTIC_PASS,
    HARNESS_SOURCE_NAMES,
    HOST_LIBIIO_CMAKE_CONFIGURATION,
    HOST_LIBIIO_RUNTIME_SCHEMA,
    HOST_LIBIIO_WRAPPER_MARKER,
    RUNNER_PROVENANCE_PATHS,
    RUNNER_PROVENANCE_SCHEMA,
    PhaseSpec,
    ReleaseCliError,
    ReleaseHardwareOptions,
    ValidatedPhase,
    _attest_host_libiio_preimport,
    _attest_imported_libiio,
    _attest_runner_provenance,
    _base_quality,
    _bind_host_libiio,
    _fingerprint,
    _harness_sources,
    _release_canonical_tandem_evidence_bytes,
    _release_tandem_metadata_dict,
    _soak_temperature_errors,
    _steady_inputs,
    _tandem_batch_pre_attack_conditioning,
    _tandem_batch_stable_suffix,
    main,
    parse_cli_args,
    phase_specs,
    plan_document,
    production_validator,
    run_aggregate,
)
from .tandem_quality import AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES
from .test_transient_hardware_oracles import (
    _FakeRadio,
    _metadata_wire,
    _quality,
    _run_fake,
    _tone_raw,
)
from .transient_hardware import (
    TRANSIENT_MODES,
    TransientCaptureOptions,
)

COMMIT = "70739d25ec1fa7b95d9069bd26a3e4192fdb3851"
FIRMWARE_VERSION = "v0.41-plutoplus-spf-tandem-agc-v8"
SHARED_HARNESS_PATHS = tuple(
    sorted(
        {
            *HARNESS_SOURCE_NAMES,
            "scripts/run_muted_metadata_batch_lifecycle_hardware.sh",
            "tests/radio_hardware/muted_metadata_batch_lifecycle.py",
        }
    )
)


def _repository() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_head() -> str:
    return subprocess.run(
        ["git", "-C", str(_repository()), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _runner_provenance() -> dict[str, Any]:
    repository = _repository()
    sources = []
    for relative in RUNNER_PROVENANCE_PATHS:
        path = repository / relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sources.append(
            {
                "path": relative,
                "absolute_path": str(path),
                "sha256": digest,
                "committed_sha256": digest,
            }
        )
    return {
        "schema": RUNNER_PROVENANCE_SCHEMA,
        "repository": str(repository),
        "commit": _git_head(),
        "clean": True,
        "sources": sources,
    }


def _runner_attestor() -> dict[str, Any]:
    return _runner_provenance()


@pytest.fixture(autouse=True)
def _stub_semantic_evidence_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Semantic mechanics are covered by tests/test_tandem_release_evidence.py."""

    def verify(index_path: Path, *, expected_stage: str) -> dict[str, Any]:
        value = json.loads(index_path.read_text())
        normalized = release_cli_module.validate_artifact_index(value)
        assert normalized["stage"] == expected_stage
        return normalized

    monkeypatch.setattr(release_cli_module, "verify_artifact_index_semantics", verify)


def _fake_host_libiio_provenance(tmp_path: Path) -> dict[str, Any]:
    private = (tmp_path / "host-libiio").resolve()
    source = private / "source"
    build = private / "build"
    binding = source / "bindings/python/iio.py"
    library = build / "libiio.so"
    cache = build / "CMakeCache.txt"
    repository = _repository()
    wrapper = repository / "scripts/run_tandem_agc_release_hardware.sh"
    wrapper_sha = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    configuration = {
        **HOST_LIBIIO_CMAKE_CONFIGURATION,
        "CMAKE_HOME_DIRECTORY": "$HOST_LIBIIO_ROOT/source",
        "PYTHON_EXECUTABLE": "/usr/bin/python3",
        "CMAKE_C_COMPILER": "/usr/bin/cc",
        "CMAKE_GENERATOR": "Unix Makefiles",
        "CMAKE_MAKE_PROGRAM": "/usr/bin/make",
    }
    binding_record = {
        "path": str(binding),
        "bytes": 101,
        "sha256": "a" * 64,
        "mode": 0o644,
    }
    library_record = {
        "path": str(library),
        "bytes": 202,
        "sha256": "b" * 64,
        "mode": 0o755,
    }
    cache_record = {
        "path": str(cache),
        "bytes": 303,
        "sha256": "c" * 64,
        "mode": 0o644,
        "configuration": configuration,
    }
    resume_identity = {
        "source_commit": COMMIT,
        "wrapper_commit": _git_head(),
        "wrapper_sha256": wrapper_sha,
        "binding_sha256": binding_record["sha256"],
        "library_sha256": library_record["sha256"],
        "cmake_configuration": configuration,
    }
    return {
        "schema": HOST_LIBIIO_RUNTIME_SCHEMA,
        "source_commit": COMMIT,
        "repository_path": str(repository),
        "private_root_path": str(private),
        "source_path": str(source),
        "build_path": str(build),
        "binding": binding_record,
        "library": library_record,
        "cmake_cache": cache_record,
        "wrapper": {
            "repository_path": str(repository),
            "commit": _git_head(),
            "path": str(wrapper),
            "sha256": wrapper_sha,
        },
        "resume_identity": resume_identity,
        "imported_binding_path": str(binding),
        "mapped_library_paths": [str(library)],
    }


def _write_binding_file(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate_roots = [parent for parent in path.parents if parent.name == "candidate"]
    if not candidate_roots:
        raise AssertionError("binding fixture path has no candidate root")
    candidate_root = candidate_roots[0]
    current = path.parent
    while True:
        os.chmod(current, 0o755)
        if current == candidate_root:
            break
        current = current.parent
    path.write_bytes(payload)
    os.chmod(path, mode)


def _write_binding_json(path: Path, value: object, *, mode: int = 0o644) -> bytes:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    _write_binding_file(path, payload, mode=mode)
    return payload


def _candidate_binding_files(tmp_path: Path) -> dict[str, Any]:
    root = (tmp_path / "candidate").resolve()
    index_path = root / "candidate-index.json"
    receipt_path = root / "hardware/deploy/radio-a/ram-boot-receipt.json"
    if root.exists():
        return {
            "root": root,
            "index": index_path,
            "receipt": receipt_path,
            "manifest": root / "source/tandem-agc-v8-source.yaml",
            "dfu": root / "artifact/firmware.dfu",
        }
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o755)
    repository = _repository()
    manifest_path = root / "source/tandem-agc-v8-source.yaml"
    manifest_payload = (repository / "manifests/tandem-agc-v8-source.yaml").read_bytes()
    _write_binding_file(manifest_path, manifest_payload)
    dfu_path = root / "artifact/firmware.dfu"
    fit_payload = b"release-candidate-fit"
    dfu_payload = fit_payload + b"D" * 16
    _write_binding_file(dfu_path, dfu_payload)

    harness_files = []
    live_harness = dict(_harness_sources())
    assert tuple(live_harness) == HARNESS_SOURCE_NAMES
    for relative in SHARED_HARNESS_PATHS:
        payload = (repository / relative).read_bytes()
        _write_binding_file(root / relative, payload)
        harness_files.append(
            {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}
        )

    evidence_members = []
    for position, role in enumerate(REQUIRED_EVIDENCE_ROLES, 1):
        relative = f"evidence/{role}.evidence"
        payload = f"{position}:{role}\n".encode()
        _write_binding_file(root / relative, payload)
        evidence_members.append(
            {
                "role": role,
                "path": relative,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    artifact_index = {
        "schema": "plutosdr-fw.tandem-release-evidence",
        "schema_version": 1,
        "stage": "candidate-pre-hardware",
        "release": {
            "firmware_version": FIRMWARE_VERSION,
            "kernel_version": "5.15.0-g77a1f2352162",
            "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)",
            "metadata_abi": "frame-metadata-v5",
            "tandem_agc": "request-v2",
        },
        "source": {
            "commit": _git_head(),
            "manifest_path": manifest_path.relative_to(root).as_posix(),
            "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        },
        "build": {"run_id": 1234, "run_attempt": 1},
        "artifact": {
            "dfu_path": dfu_path.relative_to(root).as_posix(),
            "dfu_bytes": len(dfu_payload),
            "dfu_sha256": hashlib.sha256(dfu_payload).hexdigest(),
            "fit_bytes": len(fit_payload),
            "fit_sha256": hashlib.sha256(fit_payload).hexdigest(),
        },
        "harness": {"files": harness_files},
        "evidence": {"members": evidence_members},
    }
    index_payload = _write_binding_json(index_path, artifact_index)
    receipt = {
        "schema": "plutosdr-fw.tandem-ram-boot-receipt",
        "schema_version": 4,
        "verdict": "pass",
        "boot_mode": "ram-only",
        "artifact_index_sha256": hashlib.sha256(index_payload).hexdigest(),
        "radio": {"serial": "radio-a"},
        "artifact": {"dfu_sha256": artifact_index["artifact"]["dfu_sha256"]},
        "runtime": {
            "firmware_version": FIRMWARE_VERSION,
            "hardware_model": "Analog Devices PlutoSDR Rev.C (Z7010-AD9361)",
        },
        "boot": {"pre_id": "boot-before", "post_id": "boot-after"},
        "persistent_flash": {
            "partition": "/dev/mtdblock3",
            "mtd_name": "qspi-linux",
            "bytes": 32 * 1024 * 1024,
            "pre_sha256": "7" * 64,
            "post_sha256": "7" * 64,
            "unchanged": True,
        },
        "safety": {
            "final_tx_muted": True,
            "final_dds_disabled": True,
            "final_dac_selectors_zero": True,
            "final_tandem_state": "IDLE",
            "final_fifo_level": 0,
            "final_fault_flags": 0,
        },
        "timestamps": {"started_unix_ns": 100, "completed_unix_ns": 200},
        "topology": {
            "usb_port": "3-8",
            "pre_sysfs_path": "/sys/bus/usb/devices/3-8",
            "dfu_sysfs_path": "/sys/bus/usb/devices/3-8",
            "post_sysfs_path": "/sys/bus/usb/devices/3-8",
            "network_interface": "enx001122334455",
        },
        "host_route": {
            "destination": "192.168.2.1/32",
            "interface": "enx001122334455",
            "source": "192.168.2.10",
            "release_verified": True,
        },
        "commands": [
            {
                "phase": "request-ram-mode",
                "argv": [
                    "sshpass",
                    "-f",
                    "/private/ssh-password",
                    "ssh",
                    "-F",
                    "/dev/null",
                    "-B",
                    "enx001122334455",
                    "-o",
                    "BatchMode=no",
                    "-o",
                    "NumberOfPasswordPrompts=1",
                    "-o",
                    "PreferredAuthentications=password",
                    "-o",
                    "PasswordAuthentication=yes",
                    "-o",
                    "PubkeyAuthentication=no",
                    "-o",
                    "KbdInteractiveAuthentication=no",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "GlobalKnownHostsFile=/dev/null",
                    "-o",
                    "CheckHostIP=no",
                    "-o",
                    "UpdateHostKeys=no",
                    "root@192.168.2.1",
                    "/usr/sbin/device_reboot ram",
                ],
            },
            {
                "phase": "download-firmware-to-ram",
                "argv": [
                    "dfu-util",
                    "-d",
                    "0456:b673,0456:b674",
                    "-p",
                    "3-8",
                    "-a",
                    "firmware.dfu",
                    "-D",
                    "/proc/self/fd/9",
                ],
            },
            {
                "phase": "detach-into-downloaded-image",
                "argv": [
                    "dfu-util",
                    "-d",
                    "0456:b673,0456:b674",
                    "-p",
                    "3-8",
                    "-a",
                    "firmware.dfu",
                    "-e",
                ],
            },
        ],
    }
    _write_binding_json(receipt_path, receipt, mode=0o600)
    build_utility_deployment_bundle(
        root=root,
        artifact_index_path=index_path,
        artifact_index=artifact_index,
        artifact_index_payload=index_payload,
        serial="radio-a",
        expected_current_firmware="v0.41-plutoplus-spf-tandem-agc-v8-rc12",
    )
    return {
        "root": root,
        "index": index_path,
        "receipt": receipt_path,
        "manifest": manifest_path,
        "dfu": dfu_path,
    }


def _arguments(tmp_path: Path, *extra: str) -> list[str]:
    binding = _candidate_binding_files(tmp_path)
    return [
        "--authorize-tx2-loopback",
        "--radio-serial",
        "radio-a",
        "--firmware-version",
        FIRMWARE_VERSION,
        "--artifact-index",
        str(binding["index"]),
        "--deployment-receipt",
        str(binding["receipt"]),
        "--physical-attenuation-db",
        "0",
        "--output",
        str(tmp_path / "release"),
        *extra,
    ]


def _parse(tmp_path: Path, *extra: str):
    options = parse_cli_args(
        _arguments(tmp_path, *extra),
        environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
        runner_attestor=_runner_attestor,
    )
    if options.plan_only:
        return options
    provenance = _fake_host_libiio_provenance(tmp_path)
    return _bind_host_libiio(
        options,
        lambda: json.loads(json.dumps(provenance)),
    )


def test_parser_requires_explicit_authorization_and_env_pinned_libiio(
    tmp_path: Path,
) -> None:
    arguments = _arguments(tmp_path)
    arguments.remove("--authorize-tx2-loopback")
    with pytest.raises(SystemExit):
        parse_cli_args(arguments, environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT})
    with pytest.raises(SystemExit):
        parse_cli_args(_arguments(tmp_path), environ={})


def test_parser_rejects_semantically_invalid_evidence_before_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject(_path: Path, *, expected_stage: str) -> dict[str, Any]:
        assert expected_stage == "candidate-pre-hardware"
        raise release_cli_module.EvidenceError("planted incoherent bundle")

    monkeypatch.setattr(release_cli_module, "verify_artifact_index_semantics", reject)
    with pytest.raises(SystemExit):
        parse_cli_args(
            _arguments(tmp_path, "--plan-only"),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )


@pytest.mark.parametrize("option", ["--artifact-index", "--deployment-receipt"])
def test_parser_requires_both_candidate_binding_paths(
    tmp_path: Path, option: str
) -> None:
    arguments = _arguments(tmp_path)
    position = arguments.index(option)
    del arguments[position : position + 2]

    with pytest.raises(SystemExit):
        parse_cli_args(
            arguments,
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )


@pytest.mark.parametrize("option", ["--artifact-index", "--deployment-receipt"])
def test_parser_rejects_missing_and_noncanonical_binding_paths(
    tmp_path: Path, option: str
) -> None:
    arguments = _arguments(tmp_path)
    position = arguments.index(option) + 1
    original = Path(arguments[position])
    arguments[position] = f"{original.parent}/./missing.json"

    with pytest.raises(SystemExit):
        parse_cli_args(
            arguments,
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )


@pytest.mark.parametrize("member", ["index", "receipt", "manifest", "dfu"])
def test_parser_rejects_symlinked_candidate_binding_members(
    tmp_path: Path, member: str
) -> None:
    binding = _candidate_binding_files(tmp_path)
    arguments = _arguments(tmp_path)
    original = Path(binding[member])
    if member in {"index", "receipt"}:
        link = original.with_name(f"linked-{original.name}")
        link.symlink_to(original)
        option = "--artifact-index" if member == "index" else "--deployment-receipt"
        arguments[arguments.index(option) + 1] = str(link)
    else:
        target = original.with_name(f"real-{original.name}")
        original.rename(target)
        original.symlink_to(target.name)

    with pytest.raises(SystemExit):
        parse_cli_args(
            arguments,
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )


@pytest.mark.parametrize("member", ["index", "receipt", "manifest", "dfu"])
def test_parser_rejects_missing_candidate_binding_members(
    tmp_path: Path, member: str
) -> None:
    binding = _candidate_binding_files(tmp_path)
    arguments = _arguments(tmp_path)
    Path(binding[member]).unlink()

    with pytest.raises(SystemExit):
        parse_cli_args(
            arguments,
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )


@pytest.mark.parametrize(
    "plant",
    ["serial", "firmware", "dfu", "index-receipt", "source-commit"],
)
def test_parser_rejects_mismatched_candidate_and_receipt_bindings(
    tmp_path: Path, plant: str
) -> None:
    binding = _candidate_binding_files(tmp_path)
    index_path = Path(binding["index"])
    receipt_path = Path(binding["receipt"])
    index = json.loads(index_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if plant == "serial":
        receipt["target"]["serial"] = "radio-b"
        _write_binding_json(receipt_path, receipt, mode=0o600)
    elif plant == "firmware":
        index["release"]["firmware_version"] = f"{FIRMWARE_VERSION}-decoy"
        _write_binding_json(index_path, index)
    elif plant == "dfu":
        dfu_path = Path(binding["dfu"])
        payload = bytearray(dfu_path.read_bytes())
        payload[0] ^= 0xFF
        _write_binding_file(dfu_path, bytes(payload))
    elif plant == "index-receipt":
        candidate_path = receipt_path.parent / "release-candidate-plan.json"
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        candidate["artifact_index"]["sha256"] = "0" * 64
        _write_binding_json(candidate_path, candidate, mode=0o600)
    else:
        index["source"]["commit"] = "0" * 40
        _write_binding_json(index_path, index)

    with pytest.raises(SystemExit):
        parse_cli_args(
            _arguments(tmp_path),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )


def test_parser_requires_release_and_receipt_harness_subset_and_rehashes_superset(
    tmp_path: Path,
) -> None:
    missing = _candidate_binding_files(tmp_path / "missing-required")
    missing_index_path = Path(missing["index"])
    missing_index = json.loads(missing_index_path.read_text(encoding="utf-8"))
    missing_index["harness"]["files"] = [
        entry
        for entry in missing_index["harness"]["files"]
        if entry["path"] != "scripts/deploy_tandem_agc_ram_hardware.sh"
    ]
    _write_binding_json(missing_index_path, missing_index)
    with pytest.raises(SystemExit):
        parse_cli_args(
            _arguments(tmp_path / "missing-required"),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )

    changed = _candidate_binding_files(tmp_path / "changed-superset")
    lifecycle_member = (
        Path(changed["root"]) / "tests/radio_hardware/muted_metadata_batch_lifecycle.py"
    )
    payload = bytearray(lifecycle_member.read_bytes())
    payload[0] ^= 0xFF
    _write_binding_file(lifecycle_member, bytes(payload))
    with pytest.raises(SystemExit):
        parse_cli_args(
            _arguments(tmp_path / "changed-superset"),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )


def test_parser_rejects_duplicate_json_keys_unsafe_modes_and_hardlinks(
    tmp_path: Path,
) -> None:
    binding = _candidate_binding_files(tmp_path / "duplicate")
    index_path = Path(binding["index"])
    payload = index_path.read_bytes()
    planted = b'{"schema":"decoy",' + payload[1:]
    _write_binding_file(index_path, planted)
    with pytest.raises(SystemExit):
        parse_cli_args(
            _arguments(tmp_path / "duplicate"),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )

    binding = _candidate_binding_files(tmp_path / "mode")
    os.chmod(binding["receipt"], 0o644)
    with pytest.raises(SystemExit):
        parse_cli_args(
            _arguments(tmp_path / "mode"),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )

    binding = _candidate_binding_files(tmp_path / "hardlink")
    os.link(binding["index"], binding["root"] / "index-hardlink.json")
    with pytest.raises(SystemExit):
        parse_cli_args(
            _arguments(tmp_path / "hardlink"),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )


def test_parser_rejects_a_candidate_file_changed_during_guarded_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = _candidate_binding_files(tmp_path)
    index_path = Path(binding["index"])
    index_inode = index_path.stat().st_ino
    original_read = os.read
    planted = False

    def racing_read(descriptor: int, count: int) -> bytes:
        nonlocal planted
        chunk = original_read(descriptor, count)
        if not planted and chunk and os.fstat(descriptor).st_ino == index_inode:
            planted = True
            with index_path.open("ab") as stream:
                stream.write(b" ")
        return chunk

    monkeypatch.setattr(release_cli_module.os, "read", racing_read)
    with pytest.raises(SystemExit):
        parse_cli_args(
            _arguments(tmp_path),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )
    assert planted is True


def test_parser_anchors_literal_firmware_and_scopes_output_by_serial(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--plan-only")

    assert options.firmware_pattern == (r"\Av0\.41\-plutoplus\-spf\-tandem\-agc\-v8\Z")
    assert options.output_dir == (tmp_path / "release" / "radio-a").resolve()
    assert set(dict(options.harness_sources)) >= {
        "tests/radio_hardware/release_cli.py",
        "tests/radio_hardware/release_campaign.py",
        "tests/radio_hardware/transient_hardware.py",
        "tests/radio_hardware/modulated_hardware.py",
    }
    assert all(len(digest) == 64 for _name, digest in options.harness_sources)
    plan = plan_document(options)
    assert plan["deployment_performed"] is False
    assert plan["configuration"]["modulated_tx2_gain_db"] == -42.0
    assert plan["configuration"]["autonomous_native_gain_control_modes"] == [
        "slow_attack",
        "fast_attack",
    ]
    assert plan["configuration"]["modulated_modes"] == list(RELEASE_MODULATED_MODES)
    assert MODE_NATIVE_HYBRID not in plan["configuration"]["modulated_modes"]


def test_plan_fingerprint_binds_release_harness_source_manifest(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--plan-only")
    planted_sources = (
        *options.harness_sources[:-1],
        (options.harness_sources[-1][0], "0" * 64),
    )

    assert _fingerprint(options, phase_specs(options)) != _fingerprint(
        replace(options, harness_sources=planted_sources), phase_specs(options)
    )
    with pytest.raises(ReleaseCliError, match="changed|bind"):
        plan_document(replace(options, harness_sources=planted_sources))


def test_parser_rejects_serial_path_traversal_before_output_join(
    tmp_path: Path,
) -> None:
    arguments = _arguments(tmp_path)
    arguments[arguments.index("radio-a")] = "../radio-a"
    with pytest.raises(SystemExit):
        parse_cli_args(
            arguments,
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
        )


def test_parser_rejects_precreated_serial_output_symlink(tmp_path: Path) -> None:
    base = tmp_path / "release"
    outside = tmp_path / "outside"
    base.mkdir()
    outside.mkdir()
    (base / "radio-a").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SystemExit):
        _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")


def test_aggregate_rechecks_serial_symlink_swap_before_executor(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    outside = tmp_path / "outside"
    outside.mkdir()
    options.output_dir.parent.mkdir(parents=True, exist_ok=True)
    options.output_dir.symlink_to(outside, target_is_directory=True)
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)

    with pytest.raises(ReleaseCliError, match="symlink"):
        run_aggregate(options, execute, validate)
    assert calls == []


def test_aggregate_rejects_precreated_attempt_symlink_before_executor(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    spec = phase_specs(options)[0]
    attempt = options.output_dir / "artifacts" / spec.key / "attempt-0001"
    outside = tmp_path / "outside-attempt"
    attempt.parent.mkdir(parents=True, exist_ok=True)
    outside.mkdir()
    attempt.symlink_to(outside, target_is_directory=True)
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)

    with pytest.raises(ReleaseCliError, match="symlink"):
        run_aggregate(options, execute, validate)
    assert calls == []


def test_characterization_and_baseline_soak_are_distinct_plans(
    tmp_path: Path,
) -> None:
    characterization = _parse(tmp_path / "characterization", "--phase", "steady")
    soak = _parse(tmp_path / "soak", "--phase", "steady", "--policy-set", "baseline")

    assert phase_specs(characterization)[0].key == "steady_characterization"
    assert characterization.repeat_cycles == 1
    assert phase_specs(soak)[0].key == "steady_soak"
    assert soak.repeat_cycles == 4
    assert soak.cycle_interval_seconds == 1_200.0
    full_config, full_base = _steady_inputs(
        characterization, characterization.output_dir / "work"
    )
    soak_config, soak_base = _steady_inputs(soak, soak.output_dir / "work")
    full_factors = {
        policy.factor
        for policy in build_release_plan(full_config, full_base).policy_cases
    }
    assert full_factors == {
        "baseline",
        "low_power_threshold",
        "large_lmt_threshold",
        "adc_thresholds",
        "low_power_dwell",
        "cooldown",
    }
    assert build_release_plan(soak_config, soak_base).policy_cases == (
        soak_config.policy_cases
    )
    assert soak_config.policy_cases[0].factor == "baseline"
    assert full_base.native_gain_control_modes == AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES
    assert soak_base.native_gain_control_modes == AUTONOMOUS_NATIVE_GAIN_CONTROL_MODES


def test_default_full_plan_keeps_2450_diagnostic_non_authorizing_and_last(
    tmp_path: Path,
) -> None:
    full = _parse(tmp_path / "full")
    soak = _parse(tmp_path / "soak", "--policy-set", "baseline")

    assert [(band.name, band.center_frequency_hz) for band in full.bands] == [
        ("lnb-low-1050mhz", 1_050_000_000),
        ("lnb-mid-1550mhz", 1_550_000_000),
        ("lnb-high-2050mhz", 2_050_000_000),
        ("table3-sentinel-5800mhz", 5_800_000_000),
    ]
    specs = phase_specs(full)
    assert len(specs) == 10
    assert specs[-1] == PhaseSpec("diagnostic_2450mhz", "diagnostic", DIAGNOSTIC_BAND)
    assert soak.phases == ("steady",)
    assert phase_specs(soak) == (PhaseSpec("steady_soak", "steady"),)


@pytest.mark.parametrize("outcome", [DIAGNOSTIC_PASS, DIAGNOSTIC_FAIL])
def test_safe_2450_outcome_completes_without_changing_authorizing_verdict(
    tmp_path: Path,
    outcome: str,
) -> None:
    options = _parse(tmp_path, "--phase", "diagnostic-2450")
    calls: list[tuple[str, str]] = []

    def execute(spec: PhaseSpec, work_dir: Path) -> Path:
        calls.append((spec.key, work_dir.name))
        path = work_dir / "diagnostic.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
        return path

    def validate(_spec: PhaseSpec, _path: Path, _work_dir: Path) -> ValidatedPhase:
        return ValidatedPhase(outcome, True, {"outcome": outcome})

    report, _path = run_aggregate(options, execute, validate)

    assert report["verdict"] == "pass"
    assert report["diagnostics"] == {"diagnostic_2450mhz": outcome}
    assert report["phases"]["diagnostic_2450mhz"]["phase_verdict"] == outcome
    assert calls == [("diagnostic_2450mhz", "attempt-0001")]


def test_2450_cleanup_failure_remains_fatal(tmp_path: Path) -> None:
    options = _parse(tmp_path, "--phase", "diagnostic-2450")
    calls: list[tuple[str, str]] = []
    execute, _validator = _fake_boundaries(calls)

    def unsafe(_spec: PhaseSpec, _path: Path, _work_dir: Path) -> ValidatedPhase:
        return ValidatedPhase(DIAGNOSTIC_FAIL, False, {})

    report, _path = run_aggregate(options, execute, unsafe)

    assert report["verdict"] == "invalid"
    assert report["phases"]["diagnostic_2450mhz"]["status"] == "failed"


def _fake_boundaries(calls: list[tuple[str, str]]):
    def execute(spec: PhaseSpec, work_dir: Path) -> Path:
        calls.append((spec.key, work_dir.name))
        path = work_dir / "fake-report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"key": spec.key, "verdict": "pass", "cleanup": True}) + "\n",
            encoding="utf-8",
        )
        return path

    def validate(spec: PhaseSpec, path: Path, _work_dir: Path) -> ValidatedPhase:
        report = json.loads(path.read_text(encoding="utf-8"))
        return ValidatedPhase(
            str(report["verdict"]),
            report.get("cleanup") is True,
            {"key": spec.key},
        )

    return execute, validate


def test_binding_hashes_and_ids_reach_plan_checkpoint_report_and_fingerprint(
    tmp_path: Path,
) -> None:
    options = _parse(
        tmp_path,
        "--phase",
        "transient",
        "--band",
        "low=915000000",
    )
    plan = plan_document(options)
    binding = plan["configuration"]["candidate_binding"]
    host_libiio = plan["configuration"]["host_libiio"]
    assert binding["serial"] == "radio-a"
    assert binding["firmware_version"] == FIRMWARE_VERSION
    assert binding["source_commit"] == _git_head()
    assert binding["build_run_id"] == 1234
    assert (
        binding["artifact_index_sha256"]
        == hashlib.sha256(options.artifact_index_path.read_bytes()).hexdigest()
    )
    assert (
        binding["deployment_receipt_sha256"]
        == hashlib.sha256(options.deployment_receipt_path.read_bytes()).hexdigest()
    )
    assert binding["deployment_boot_pre_id"] == "11111111-1111-4111-8111-111111111111"
    assert binding["deployment_boot_post_id"] == "22222222-2222-4222-8222-222222222222"
    assert len(binding["evidence_files"]) == len(REQUIRED_EVIDENCE_ROLES)
    assert (
        tuple(member["role"] for member in binding["evidence_files"])
        == REQUIRED_EVIDENCE_ROLES
    )
    indexed_harness = {
        member["relative_path"]: member for member in binding["harness_files"]
    }
    assert tuple(indexed_harness) == SHARED_HARNESS_PATHS
    assert all(
        indexed_harness[path]["required_for_release_hardware"] is True
        and indexed_harness[path]["committed_sha256"] == indexed_harness[path]["sha256"]
        for path in HARNESS_SOURCE_NAMES
    )
    assert (
        indexed_harness["tests/radio_hardware/muted_metadata_batch_lifecycle.py"][
            "required_for_release_hardware"
        ]
        is False
    )
    assert host_libiio["schema"] == HOST_LIBIIO_RUNTIME_SCHEMA
    assert host_libiio["source_commit"] == COMMIT
    assert host_libiio["resume_identity"]["binding_sha256"] == "a" * 64
    assert host_libiio["resume_identity"]["library_sha256"] == "b" * 64
    assert (
        host_libiio["resume_identity"]["cmake_configuration"]
        == host_libiio["cmake_cache"]["configuration"]
    )

    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)
    report, _path = run_aggregate(options, execute, validate)
    checkpoint = json.loads(
        (options.output_dir / AGGREGATE_CHECKPOINT).read_text(encoding="utf-8")
    )
    assert report["configuration"]["candidate_binding"] == binding
    assert checkpoint["configuration"]["candidate_binding"] == binding
    assert report["configuration"]["host_libiio"] == host_libiio
    assert checkpoint["configuration"]["host_libiio"] == host_libiio
    assert report["host_libiio_invocations"] == checkpoint["host_libiio_invocations"]
    assert report["host_libiio_invocations"][0]["provenance"] == host_libiio
    assert report["all_host_libiio_verified"] is True
    phase = report["phases"]["transient_low"]
    assert phase["host_libiio_before_phase"] == host_libiio
    assert phase["host_libiio_after_cleanup"] == host_libiio

    planted_binding = json.loads(options.candidate_binding_json)
    planted_binding["deployment_receipt_sha256"] = "0" * 64
    planted = replace(
        options,
        candidate_binding_json=json.dumps(
            planted_binding,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    assert _fingerprint(options, phase_specs(options)) != _fingerprint(
        planted, phase_specs(planted)
    )

    equivalent = _fake_host_libiio_provenance(tmp_path / "equivalent-build")
    equivalent["cmake_cache"]["sha256"] = "e" * 64
    equivalent_options = replace(
        options,
        host_libiio_json=json.dumps(equivalent, sort_keys=True, separators=(",", ":")),
        host_libiio_attestor=lambda: equivalent,
    )
    assert _fingerprint(options, phase_specs(options)) == _fingerprint(
        equivalent_options, phase_specs(equivalent_options)
    )
    changed_library = json.loads(json.dumps(equivalent))
    changed_library["library"]["sha256"] = "f" * 64
    changed_library["resume_identity"]["library_sha256"] = "f" * 64
    changed_options = replace(
        options,
        host_libiio_json=json.dumps(
            changed_library, sort_keys=True, separators=(",", ":")
        ),
        host_libiio_attestor=lambda: changed_library,
    )
    assert _fingerprint(options, phase_specs(options)) != _fingerprint(
        changed_options, phase_specs(changed_options)
    )


def test_resume_accepts_equivalent_fresh_host_libiio_build_and_records_invocation(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    first_calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(first_calls)
    first, _path = run_aggregate(options, execute, validate)
    assert first["verdict"] == "pass"

    equivalent = _fake_host_libiio_provenance(tmp_path / "fresh-rebuild")
    equivalent["cmake_cache"]["sha256"] = "e" * 64
    resumed = replace(
        options,
        host_libiio_json=json.dumps(equivalent, sort_keys=True, separators=(",", ":")),
        host_libiio_attestor=lambda: equivalent,
    )
    resumed_calls: list[tuple[str, str]] = []
    execute_resumed, validate_resumed = _fake_boundaries(resumed_calls)
    second, _path = run_aggregate(resumed, execute_resumed, validate_resumed)

    assert second["verdict"] == "pass"
    assert resumed_calls == []
    assert len(second["host_libiio_invocations"]) == 2
    assert second["host_libiio_invocations"][1]["provenance"] == equivalent


def test_aggregate_fails_closed_when_host_libiio_changes_during_cleanup(
    tmp_path: Path,
) -> None:
    options = _parse(
        tmp_path,
        "--phase",
        "transient",
        "--band",
        "low=915000000",
        "--band",
        "high=5800000000",
    )
    observed = json.loads(options.host_libiio_json or "{}")
    calls: list[str] = []

    def attest() -> dict[str, Any]:
        return json.loads(json.dumps(observed))

    options = replace(options, host_libiio_attestor=attest)

    def execute(spec: PhaseSpec, work_dir: Path) -> Path:
        calls.append(spec.key)
        report = work_dir / "fake-report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('{"verdict":"pass"}\n', encoding="utf-8")
        observed["library"]["bytes"] += 1
        return report

    def validate(spec: PhaseSpec, _path: Path, _work_dir: Path) -> ValidatedPhase:
        return ValidatedPhase("pass", True, {"key": spec.key})

    with pytest.raises(ReleaseCliError, match="host libiio"):
        run_aggregate(options, execute, validate)
    report = json.loads(
        (options.output_dir / "release-hardware-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["verdict"] == "invalid"
    assert report["all_host_libiio_verified"] is False
    assert calls == ["transient_low"]
    assert report["phases"]["transient_low"]["status"] == "failed"
    assert "host libiio" in report["phases"]["transient_low"]["error"]


def test_aggregate_reattests_host_libiio_before_each_hardware_phase(
    tmp_path: Path,
) -> None:
    options = _parse(
        tmp_path,
        "--phase",
        "transient",
        "--band",
        "low=915000000",
        "--band",
        "high=5800000000",
    )
    observed = json.loads(options.host_libiio_json or "{}")
    calls: list[str] = []

    def attest() -> dict[str, Any]:
        return json.loads(json.dumps(observed))

    options = replace(options, host_libiio_attestor=attest)

    def execute(spec: PhaseSpec, work_dir: Path) -> Path:
        calls.append(spec.key)
        report = work_dir / "fake-report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('{"verdict":"pass"}\n', encoding="utf-8")
        return report

    def validate(spec: PhaseSpec, _path: Path, _work_dir: Path) -> ValidatedPhase:
        observed["cmake_cache"]["sha256"] = "d" * 64
        return ValidatedPhase("pass", True, {"key": spec.key})

    with pytest.raises(ReleaseCliError, match="host libiio"):
        run_aggregate(options, execute, validate)
    assert calls == ["transient_low"]
    checkpoint = json.loads(
        (options.output_dir / AGGREGATE_CHECKPOINT).read_text(encoding="utf-8")
    )
    assert checkpoint["phases"]["transient_low"]["status"] == "complete"
    assert checkpoint["phases"]["transient_high"]["status"] == "pending"


def test_aggregate_reattests_inputs_before_each_hardware_phase(
    tmp_path: Path,
) -> None:
    options = _parse(
        tmp_path,
        "--phase",
        "transient",
        "--band",
        "low=915000000",
        "--band",
        "high=5800000000",
    )
    dfu_path = Path(json.loads(options.candidate_binding_json)["dfu_file"]["path"])
    calls: list[str] = []

    def execute(spec: PhaseSpec, work_dir: Path) -> Path:
        calls.append(spec.key)
        path = work_dir / "fake-report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"key": spec.key, "verdict": "pass", "cleanup": True}),
            encoding="utf-8",
        )
        if len(calls) == 1:
            payload = bytearray(dfu_path.read_bytes())
            payload[0] ^= 0xFF
            _write_binding_file(dfu_path, bytes(payload))
        return path

    def validate(spec: PhaseSpec, _path: Path, _work_dir: Path) -> ValidatedPhase:
        return ValidatedPhase("pass", True, {"key": spec.key})

    with pytest.raises(ReleaseCliError, match="DFU|changed"):
        run_aggregate(options, execute, validate)
    assert calls == ["transient_low"]
    checkpoint = json.loads(
        (options.output_dir / AGGREGATE_CHECKPOINT).read_text(encoding="utf-8")
    )
    assert checkpoint["phases"]["transient_low"]["status"] == "complete"
    assert checkpoint["phases"]["transient_high"]["status"] == "pending"


def test_plan_only_never_imports_iio_or_constructs_hardware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "iio" or name.startswith("iio."):
            raise AssertionError("plan-only attempted to import iio")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert (
        main(
            _arguments(tmp_path, "--plan-only"),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )
        == 0
    )


def test_direct_python_invocation_is_rejected_before_importing_iio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    imported_iio = False
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        nonlocal imported_iio
        if name == "iio" or name.startswith("iio."):
            imported_iio = True
            raise AssertionError("iio import must follow wrapper provenance")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(SystemExit, match="use scripts/run_tandem_agc_release_hardware"):
        main(
            _arguments(tmp_path),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=_runner_attestor,
        )
    assert imported_iio is False


def test_shell_plan_only_precedes_iio_build_and_has_no_deployer() -> None:
    shell = _repository() / "scripts/run_tandem_agc_release_hardware.sh"
    source = shell.read_text(encoding="utf-8")

    plan_branch = source.index('if [[ "${plan_only}" == true ]]')
    assert plan_branch < source.index("IIO_BUILD=")
    assert "import iio" not in source
    assert "dfu-util" not in source
    assert "-m tests.radio_hardware.tandem_ram_deploy" not in source
    assert "--porcelain=v1 --untracked-files=all" in source
    assert "IIO_BUILD reuse is forbidden" in source
    assert "--clean-first" in source
    for name in (
        "PLUTOSDR_FW_LIBIIO_REPOSITORY",
        "PLUTOSDR_FW_LIBIIO_SOURCE",
        "PLUTOSDR_FW_LIBIIO_BUILD",
        "PLUTOSDR_FW_LIBIIO_SO_PATH",
        "PLUTOSDR_FW_LIBIIO_SO_SHA256",
        "PLUTOSDR_FW_PYLIBIIO_PATH",
        "PLUTOSDR_FW_PYLIBIIO_SHA256",
        "PLUTOSDR_FW_LIBIIO_CMAKE_CACHE_PATH",
        "PLUTOSDR_FW_LIBIIO_CMAKE_CACHE_SHA256",
        "PLUTOSDR_FW_LIBIIO_PYTHON_EXECUTABLE",
        "PLUTOSDR_FW_LIBIIO_GUARDED_WRAPPER",
    ):
        assert name in source


def _host_libiio_fixture(
    tmp_path: Path,
) -> tuple[dict[str, str], Any, Path, dict[str, Path]]:
    repository = (tmp_path / "libiio-repository").resolve()
    binding = repository / "bindings/python/iio.py"
    binding.parent.mkdir(parents=True)
    binding.write_text("class MetadataBuffer: pass\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "Release Test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-q", "-m", "fixture"],
        check=True,
    )
    private = (tmp_path / "private-libiio-root").resolve()
    private.mkdir(mode=0o700)
    snapshot = private / "source"
    snapshot.mkdir(mode=0o700)
    snapshot_binding = snapshot / "bindings/python/iio.py"
    snapshot_binding.parent.mkdir(parents=True)
    snapshot_binding.write_bytes(binding.read_bytes())
    snapshot_binding.chmod(0o644)
    build = private / "build"
    build.mkdir(mode=0o700)
    library = build / "libiio.so.0.25"
    library.write_bytes(b"fresh pinned libiio\n")
    library.chmod(0o755)
    python_executable = "/usr/bin/python3"
    cmake_values = {
        **HOST_LIBIIO_CMAKE_CONFIGURATION,
        "CMAKE_HOME_DIRECTORY": str(snapshot),
        "PYTHON_EXECUTABLE": python_executable,
        "CMAKE_C_COMPILER": "/usr/bin/cc",
        "CMAKE_GENERATOR": "Unix Makefiles",
        "CMAKE_MAKE_PROGRAM": "/usr/bin/make",
    }
    cache = build / "CMakeCache.txt"
    cache.write_text(
        "".join(f"{key}:STRING={value}\n" for key, value in cmake_values.items()),
        encoding="utf-8",
    )
    cache.chmod(0o644)
    maps = tmp_path / "maps"
    maps.write_text(
        f"00000000-00001000 r-xp 00000000 00:00 0 {library}\n",
        encoding="utf-8",
    )
    wrapper_repository = _repository()
    wrapper = wrapper_repository / "scripts/run_tandem_agc_release_hardware.sh"
    wrapper_sha = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    environment = {
        "PLUTOSDR_FW_LIBIIO_GUARDED_WRAPPER": HOST_LIBIIO_WRAPPER_MARKER,
        "PLUTOSDR_FW_LIBIIO_REPOSITORY": str(repository),
        "PLUTOSDR_FW_LIBIIO_SOURCE": str(snapshot),
        "PLUTOSDR_FW_LIBIIO_BUILD": str(build),
        "PLUTOSDR_FW_LIBIIO_SO_PATH": str(library),
        "PLUTOSDR_FW_LIBIIO_SO_SHA256": hashlib.sha256(
            library.read_bytes()
        ).hexdigest(),
        "PLUTOSDR_FW_PYLIBIIO_PATH": str(snapshot_binding),
        "PLUTOSDR_FW_PYLIBIIO_SHA256": hashlib.sha256(
            snapshot_binding.read_bytes()
        ).hexdigest(),
        "PLUTOSDR_FW_LIBIIO_CMAKE_CACHE_PATH": str(cache),
        "PLUTOSDR_FW_LIBIIO_CMAKE_CACHE_SHA256": hashlib.sha256(
            cache.read_bytes()
        ).hexdigest(),
        "PLUTOSDR_FW_LIBIIO_PYTHON_EXECUTABLE": python_executable,
        "PLUTOSDR_FW_RUNNER_REPOSITORY": str(wrapper_repository),
        "PLUTOSDR_FW_RUNNER_COMMIT": _git_head(),
        "PLUTOSDR_FW_RUNNER_SHELL_PATH": str(wrapper),
        "PLUTOSDR_FW_RUNNER_SHELL_SHA256": wrapper_sha,
        "PLUTOSDR_FW_RUNNER_SHELL_COMMITTED_SHA256": wrapper_sha,
    }
    module = type(
        "PinnedIio",
        (),
        {"__file__": str(snapshot_binding), "MetadataBuffer": object()},
    )
    return (
        environment,
        module,
        maps,
        {
            "binding": snapshot_binding,
            "library": library,
            "cache": cache,
        },
    )


def test_imported_libiio_requires_clean_source_fresh_build_and_exact_bytes(
    tmp_path: Path,
) -> None:
    environment, module, maps, files = _host_libiio_fixture(tmp_path)
    attestation = _attest_imported_libiio(
        module,
        environment,
        expected_commit=subprocess.run(
            [
                "git",
                "-C",
                environment["PLUTOSDR_FW_LIBIIO_REPOSITORY"],
                "rev-parse",
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        maps_path=maps,
    )
    assert attestation["schema"] == HOST_LIBIIO_RUNTIME_SCHEMA
    assert (
        attestation["library"]["sha256"] == environment["PLUTOSDR_FW_LIBIIO_SO_SHA256"]
    )
    assert (
        attestation["cmake_cache"]["sha256"]
        == environment["PLUTOSDR_FW_LIBIIO_CMAKE_CACHE_SHA256"]
    )
    # The pinned libiio repository and firmware runner repository are
    # intentionally distinct.  The durable validator must bind the wrapper to
    # the latter rather than accidentally resolving it beneath the former.
    assert (
        release_cli_module._validate_host_libiio_runtime(attestation)["wrapper"]
        == attestation["wrapper"]
    )

    files["library"].write_bytes(b"substituted library\n")
    with pytest.raises(ReleaseCliError, match="bytes changed"):
        _attest_imported_libiio(
            module,
            environment,
            expected_commit=attestation["source_commit"],
            maps_path=maps,
        )


def test_host_libiio_rejects_self_hashed_cache_without_guarded_wrapper(
    tmp_path: Path,
) -> None:
    environment, _module, _maps, _files = _host_libiio_fixture(tmp_path)
    environment.pop("PLUTOSDR_FW_LIBIIO_GUARDED_WRAPPER")

    with pytest.raises(ReleaseCliError, match="guarded.*wrapper"):
        _attest_host_libiio_preimport(
            environment,
            expected_commit=subprocess.run(
                [
                    "git",
                    "-C",
                    environment["PLUTOSDR_FW_LIBIIO_REPOSITORY"],
                    "rev-parse",
                    "HEAD",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
        )


def test_host_libiio_rejects_rehashed_nonrelease_cmake_configuration(
    tmp_path: Path,
) -> None:
    environment, _module, _maps, files = _host_libiio_fixture(tmp_path)
    cache = files["cache"]
    cache.write_text(
        cache.read_text(encoding="utf-8").replace(
            "WITH_USB_BACKEND:STRING=ON", "WITH_USB_BACKEND:STRING=OFF"
        ),
        encoding="utf-8",
    )
    cache.chmod(0o644)
    environment["PLUTOSDR_FW_LIBIIO_CMAKE_CACHE_SHA256"] = hashlib.sha256(
        cache.read_bytes()
    ).hexdigest()

    with pytest.raises(ReleaseCliError, match="CMake configuration changed"):
        _attest_host_libiio_preimport(
            environment,
            expected_commit=subprocess.run(
                [
                    "git",
                    "-C",
                    environment["PLUTOSDR_FW_LIBIIO_REPOSITORY"],
                    "rev-parse",
                    "HEAD",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
        )


def test_host_libiio_rejects_cmake_cache_mutation_during_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment, _module, _maps, files = _host_libiio_fixture(tmp_path)
    cache = files["cache"]
    cache_inode = cache.stat().st_ino
    original_read = os.read
    mutated = False

    def racing_read(descriptor: int, size: int) -> bytes:
        nonlocal mutated
        if not mutated and os.fstat(descriptor).st_ino == cache_inode:
            mutated = True
            with cache.open("ab") as stream:
                stream.write(b"# planted race\n")
        return original_read(descriptor, size)

    monkeypatch.setattr(os, "read", racing_read)
    with pytest.raises(ReleaseCliError, match="changed while it was read"):
        _attest_host_libiio_preimport(
            environment,
            expected_commit=subprocess.run(
                [
                    "git",
                    "-C",
                    environment["PLUTOSDR_FW_LIBIIO_REPOSITORY"],
                    "rev-parse",
                    "HEAD",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
        )
    assert mutated is True


def test_parser_rejects_malformed_test_runner_provenance(tmp_path: Path) -> None:
    provenance = _runner_provenance()
    provenance["clean"] = False

    with pytest.raises(SystemExit):
        parse_cli_args(
            _arguments(tmp_path),
            environ={"PLUTOSDR_FW_LIBIIO_SOURCE_COMMIT": COMMIT},
            runner_attestor=lambda: provenance,
        )


def test_production_runner_attestor_requires_exact_committed_clean_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = (tmp_path / "runner-repository").resolve()
    repository.mkdir()
    source_paths: dict[str, Path] = {}
    for relative in RUNNER_PROVENANCE_PATHS:
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"committed runner source: {relative}\n", encoding="utf-8")
        os.chmod(path, 0o644)
        source_paths[relative] = path

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Release Oracle")
    git("config", "user.email", "release-oracle@example.invalid")
    git("add", ".")
    git("commit", "-q", "-m", "runner fixture")
    commit = git("rev-parse", "HEAD")
    environment = {
        "PLUTOSDR_FW_RUNNER_REPOSITORY": str(repository),
        "PLUTOSDR_FW_RUNNER_COMMIT": commit,
    }
    stems = {
        "scripts/deploy_tandem_agc_ram_hardware.sh": "DEPLOY_SHELL",
        "scripts/run_tandem_agc_release_hardware.sh": "SHELL",
        "scripts/tandem_release_device_plan.py": "DEVICE_PLAN",
        "scripts/tandem_release_evidence.py": "SEMANTIC_EVIDENCE",
        "tests/radio_hardware/candidate_binding.py": "CANDIDATE_BINDING",
        "tests/radio_hardware/pluto_plus_candidate.py": "PLUTO_PLUS_CANDIDATE",
        "tests/radio_hardware/release_cli.py": "RELEASE_CLI",
    }
    for relative, path in source_paths.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stem = stems[relative]
        environment[f"PLUTOSDR_FW_RUNNER_{stem}_PATH"] = str(path)
        environment[f"PLUTOSDR_FW_RUNNER_{stem}_SHA256"] = digest
        environment[f"PLUTOSDR_FW_RUNNER_{stem}_COMMITTED_SHA256"] = digest

    monkeypatch.setattr(
        release_cli_module,
        "__file__",
        str(source_paths["tests/radio_hardware/release_cli.py"]),
    )
    provenance = _attest_runner_provenance(environment)
    assert provenance["commit"] == commit
    assert provenance["clean"] is True
    assert tuple(source["path"] for source in provenance["sources"]) == (
        RUNNER_PROVENANCE_PATHS
    )

    (repository / "untracked-decoy").write_text("decoy\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="fully clean"):
        _attest_runner_provenance(environment)


def test_fake_aggregate_requires_every_requested_phase_and_cleanup(
    tmp_path: Path,
) -> None:
    options = _parse(
        tmp_path,
        "--phase",
        "transient",
        "--band",
        "low=915000000",
        "--band",
        "high=5800000000",
    )
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)

    report, report_path = run_aggregate(options, execute, validate)

    assert report_path.is_file()
    assert report["verdict"] == "pass"
    assert report["all_requested_phases_complete"] is True
    assert report["all_cleanup_verified"] is True
    assert [key for key, _attempt in calls] == [
        "transient_low",
        "transient_high",
    ]


def test_resume_revalidates_hash_and_never_reruns_completed_artifact(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)
    first, _path = run_aggregate(options, execute, validate)
    artifact = Path(first["phases"]["transient_low"]["report_path"])
    artifact.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ReleaseCliError, match="artifact changed"):
        run_aggregate(options, execute, validate)
    assert len(calls) == 1


def test_resume_accepts_canonicalized_multi_phase_checkpoint_order(
    tmp_path: Path,
) -> None:
    options = _parse(
        tmp_path,
        "--phase",
        "transient",
        "--band",
        "low=915000000",
        "--band",
        "high=5800000000",
    )
    first_calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(first_calls)
    first, _path = run_aggregate(options, execute, validate)
    assert first["verdict"] == "pass"
    assert first_calls == [
        ("transient_low", "attempt-0001"),
        ("transient_high", "attempt-0001"),
    ]

    checkpoint_path = options.output_dir / AGGREGATE_CHECKPOINT
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert list(checkpoint["phases"]) == ["transient_high", "transient_low"]

    resumed_calls: list[tuple[str, str]] = []
    execute_resumed, validate_resumed = _fake_boundaries(resumed_calls)
    resumed, _path = run_aggregate(options, execute_resumed, validate_resumed)
    assert resumed["verdict"] == "pass"
    assert resumed_calls == []


def test_resume_rejects_tampered_phase_spec(tmp_path: Path) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)
    first, _path = run_aggregate(options, execute, validate)
    assert first["verdict"] == "pass"

    checkpoint_path = options.output_dir / AGGREGATE_CHECKPOINT
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["phases"]["transient_low"]["spec"]["kind"] = "modulated"
    checkpoint_path.write_text(
        json.dumps(checkpoint, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(ReleaseCliError, match="differs from the requested plan"):
        run_aggregate(options, execute, validate)


def test_interrupted_artifact_is_abandoned_and_fresh_attempt_is_used(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "transient", "--band", "low=915000000")
    specs = phase_specs(options)
    calls: list[tuple[str, str]] = []
    execute, validate = _fake_boundaries(calls)
    # Plant a valid new checkpoint, then model power loss after the running mark.
    from .release_cli import _atomic_json, _new_checkpoint

    checkpoint = _new_checkpoint(options, specs)
    record = checkpoint["phases"]["transient_low"]
    record.update(
        {
            "status": "running",
            "attempts": 1,
            "work_dir": str(options.output_dir / "artifacts" / "old"),
        }
    )
    _atomic_json(options.output_dir / AGGREGATE_CHECKPOINT, checkpoint)

    report, _path = run_aggregate(options, execute, validate)

    assert report["verdict"] == "pass"
    assert calls == [("transient_low", "attempt-0002")]
    history = report["phases"]["transient_low"]["history"]
    assert history[0]["status"] == "abandoned_untrusted_interrupted_attempt"


def test_incomplete_steady_stops_before_other_phase(tmp_path: Path) -> None:
    options = _parse(
        tmp_path,
        "--phase",
        "steady",
        "--phase",
        "transient",
        "--band",
        "low=915000000",
    )
    calls: list[str] = []

    def execute(spec: PhaseSpec, work_dir: Path) -> Path:
        calls.append(spec.key)
        path = work_dir / "fake-report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"kind": spec.kind}) + "\n", encoding="utf-8")
        return path

    def validate(spec: PhaseSpec, _path: Path, _work_dir: Path) -> ValidatedPhase:
        if spec.kind == "steady":
            return ValidatedPhase("incomplete", False, {"complete_runs": 1})
        return ValidatedPhase("pass", True, {})

    report, _path = run_aggregate(options, execute, validate)

    assert report["verdict"] == "incomplete"
    assert calls == ["steady_characterization"]
    assert report["phases"]["transient_low"]["status"] == "pending"


def test_cleanup_failure_cannot_produce_aggregate_pass(tmp_path: Path) -> None:
    options = _parse(tmp_path, "--phase", "modulated", "--band", "low=915000000")
    calls: list[tuple[str, str]] = []
    execute, _validate = _fake_boundaries(calls)

    def missing_cleanup(
        _spec: PhaseSpec, _path: Path, _work_dir: Path
    ) -> ValidatedPhase:
        return ValidatedPhase("pass", False, {})

    report, _path = run_aggregate(options, execute, missing_cleanup)

    assert report["verdict"] == "invalid"
    assert report["all_cleanup_verified"] is False
    assert report["phases"]["modulated_low"]["status"] == "failed"


def test_production_validator_compares_modulated_configuration_in_json_domain(
    tmp_path: Path,
) -> None:
    options = _parse(tmp_path, "--phase", "modulated", "--band", "low=915000000")
    spec = phase_specs(options)[0]
    work_dir = options.output_dir / "work"
    report_path = work_dir / "radio-a" / "modulated-hardware-report.json"
    modulated = ModulatedHardwareOptions(
        physical_attenuation_db=0.0,
        center_frequency_hz=915_000_000,
        tx2_gain_db=DEFAULT_MODULATED_TX2_GAIN_DB,
        max_seconds=options.phase_max_seconds,
        output_dir=work_dir,
    )
    configuration = json.loads(
        json.dumps(
            {
                **asdict(modulated),
                "output_dir": str(work_dir),
                "minimum_effective_attenuation_db": (
                    modulated.minimum_effective_attenuation_db
                ),
            },
            default=str,
        )
    )
    case_ids = [
        "desired_only",
        *(f"blocker_{index:02d}" for index in range(len(modulated.blocker_points))),
    ]
    desired_payload = (bytes(range(256)) * 256)[: modulated.capture_samples * 8]
    blocker_payload = bytes(value ^ 0xA5 for value in desired_payload)
    raw_by_case: dict[str, dict[str, object]] = {}
    for purpose, case_id, filename, payload in (
        (
            "desired_baseline",
            "desired_only",
            "desired-only-manual-fixed-frame-0000-rx0-rx1.cs16le",
            desired_payload,
        ),
        (
            "first_blocker",
            "blocker_00",
            "blocker-00-manual-fixed-frame-0000-rx0-rx1.cs16le",
            blocker_payload,
        ),
    ):
        digest = hashlib.sha256(payload).hexdigest()
        relative_path = Path(options.serial) / "diagnostic-iq" / filename
        path = work_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        raw_by_case[case_id] = {
            "payload": payload,
            "sha256": digest,
            "path": path,
            "provenance": {
                "purpose": purpose,
                "case_id": case_id,
                "mode": "manual_fixed",
                "measurement_index": 0,
                "path": relative_path.as_posix(),
                "sha256": digest,
                "bytes": len(payload),
                "encoding": "signed-16-bit-little-endian",
                "channel_layout": ["rx0_i", "rx0_q", "rx1_i", "rx1_q"],
                "samples_per_channel": modulated.capture_samples,
            },
        }

    def quality_summary(case_id: str) -> dict[str, object]:
        blocked = case_id != "desired_only"
        return {
            "schema": "plutosdr-fw.modulated-quality.v1",
            "reference_id": "reference-46",
            "iq_convention": "direct",
            "quality_valid": True,
            "quality_reasons": [],
            "evm_percent": [2.0, 2.0],
            "mer_db": [34.0, 34.0],
            "ser": [0.0, 0.0],
            "ber": [0.0, 0.0],
            "desired_gain_linear": [1.0, 1.0],
            "blocker_offset_hz": 320_000.0 if blocked else None,
            "blocker_power_db": -20.0 if blocked else None,
        }

    cleanup = {
        "verified": True,
        "failures": [],
        "tx1_gain_db": -89.75,
        "tx2_gain_db": -89.75,
        "selectors": [3, 3, 3, 3],
        "dds": {
            f"altvoltage{index}": {"present": True, "scale": 0.0, "raw": 0.0}
            for index in range(8)
        },
    }

    def tandem_frame(sequence: int) -> dict[str, object]:
        first = sequence == 0
        return {
            "metadata": {
                "buffer_sequence": sequence,
                "first_sample_sequence": sequence * modulated.capture_samples,
                "samples_per_channel": modulated.capture_samples,
                "tandem_transition_count": 0,
                "gain_events": [],
            },
            "continuity": {
                "buffer_delta": None if first else 1,
                "sample_delta": None if first else modulated.capture_samples,
                "missing_frame_count": 0,
                "transition_count_delta": None if first else 0,
                "visible_event_count": 0,
                "hidden_transition_count": 0,
                "initial_unrepresented_transition_count": 0,
                "cumulative_missing_frame_count": 0,
                "cumulative_hidden_transition_count": 0,
                "cumulative_event_sequence_hole_count": 0,
            },
        }

    def raw_measurements(case_id: str) -> list[dict[str, object]]:
        artifact = raw_by_case[case_id]
        payload = artifact["payload"]
        assert isinstance(payload, bytes)
        return [
            {
                "sha256": artifact["sha256"],
                "iq_bytes": len(payload),
                "raw_iq_provenance": artifact["provenance"],
            }
        ]

    report = {
        "schema": "plutosdr-fw.modulated-hardware.v1",
        "verdict": "pass",
        "identity": {
            "serial": options.serial,
            "uri": "usb:1.2.3",
            "libiio_source_commit": COMMIT,
            "context_attrs": {"fw_version": options.firmware_version},
        },
        "configuration": configuration,
        "mode_evidence_policy": modulated_mode_evidence_policy(),
        "rf": {"center_frequency_hz_requested": 915_000_000},
        "cleanup": cleanup,
        "waveforms": [
            {
                "case_id": case_id,
                "kind": (
                    "desired_only" if case_id == "desired_only" else "composite_blocker"
                ),
                "dma_cleanup": {
                    "mute": cleanup,
                    "buffer_closed": True,
                    "buffer_release_method": "explicit_close",
                    "failures": [],
                },
            }
            for case_id in case_ids
        ],
        "runs": [
            {
                "case_id": case_id,
                "mode": mode,
                "tx2_gain_requested_db": DEFAULT_MODULATED_TX2_GAIN_DB,
                "tx2_gain_readback_db": DEFAULT_MODULATED_TX2_GAIN_DB,
                "effective_attenuation_db": (
                    modulated.minimum_effective_attenuation_db
                ),
                "summary": quality_summary(case_id),
                **(
                    {
                        "settling": {"frames": 1, "trace": [tandem_frame(0)]},
                        "measurements": [tandem_frame(1)],
                    }
                    if mode == MODE_TANDEM
                    else (
                        {"measurements": raw_measurements(case_id)}
                        if case_id in raw_by_case and mode == "manual_fixed"
                        else {}
                    )
                ),
            }
            for case_id in case_ids
            for mode in modulated.modes
        ],
    }
    report["evaluation"] = evaluate_modulated_hardware_report(
        report,
        modulated.degradation_thresholds,
        expected_modes=modulated.modes,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    validated = production_validator(options)(spec, report_path, work_dir)

    assert validated.verdict == "pass"
    assert validated.cleanup_verified is True
    expected_raw_summary: dict[str, object] = {}
    for artifact in raw_by_case.values():
        provenance = artifact["provenance"]
        assert isinstance(provenance, dict)
        expected_raw_summary[str(provenance["purpose"])] = provenance
    assert validated.summary["raw_iq_provenance"] == expected_raw_summary

    def raw_frame(document: dict[str, object], case_id: str) -> dict[str, object]:
        runs = document["runs"]
        assert isinstance(runs, list)
        run = next(
            item
            for item in runs
            if item["case_id"] == case_id and item["mode"] == "manual_fixed"
        )
        return run["measurements"][0]

    valid_report = json.loads(json.dumps(report))
    assert modulated.modes == RELEASE_MODULATED_MODES
    assert MODE_NATIVE_HYBRID not in {run["mode"] for run in valid_report["runs"]}
    report["evaluation"]["degradation_valid"] = False
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="differs from recomputation"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["mode_evidence_policy"]["native_hybrid"]["release_qualification_claim"] = (
        True
    )
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="mode evidence policy differs"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    planted_hybrid = dict(report["runs"][0])
    planted_hybrid["mode"] = MODE_NATIVE_HYBRID
    report["runs"].append(planted_hybrid)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="mode/blocker coverage differs"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["runs"][-1]["summary"]["iq_convention"] = "conjugated"
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="IQ convention changed"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    tandem_run = next(run for run in report["runs"] if run["mode"] == MODE_TANDEM)
    tandem_run["measurements"][0]["continuity"]["sample_delta"] += 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="gap evidence differs from metadata"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["waveforms"][0]["dma_cleanup"]["mute"]["verified"] = False
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="cyclic-DMA cleanup was not verified"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["runs"][0]["tx2_gain_readback_db"] = -41.75
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="TX2 gain readback differs from plan"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    target_frame = raw_frame(report, "blocker_00")
    target_frame["raw_iq_provenance"]["path"] = "../../escaped.cs16le"
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="escapes the phase work directory"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    report["runs"][1]["measurements"] = [dict(raw_measurements("desired_only")[0])]
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="exactly two raw-IQ provenance"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    raw_frame(report, "blocker_00").pop("raw_iq_provenance")
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="exactly two raw-IQ provenance"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    raw_frame(report, "blocker_00")["raw_iq_provenance"]["channel_layout"] = [
        "rx1_i",
        "rx1_q",
        "rx0_i",
        "rx0_q",
    ]
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="channel layout differs from plan"):
        production_validator(options)(spec, report_path, work_dir)

    report = json.loads(json.dumps(valid_report))
    raw_frame(report, "blocker_00")["raw_iq_provenance"]["measurement_index"] = 1
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="frame linkage differs from plan"):
        production_validator(options)(spec, report_path, work_dir)

    report_path.write_text(json.dumps(valid_report) + "\n", encoding="utf-8")
    desired_path = raw_by_case["desired_only"]["path"]
    desired_payload = raw_by_case["desired_only"]["payload"]
    assert isinstance(desired_path, Path)
    assert isinstance(desired_payload, bytes)
    blocker_path = raw_by_case["blocker_00"]["path"]
    blocker_payload = raw_by_case["blocker_00"]["payload"]
    assert isinstance(blocker_path, Path)
    assert isinstance(blocker_payload, bytes)

    report = json.loads(json.dumps(valid_report))
    desired_digest = hashlib.sha256(desired_payload).hexdigest()
    blocker_frame = raw_frame(report, "blocker_00")
    blocker_frame["sha256"] = desired_digest
    blocker_frame["raw_iq_provenance"]["sha256"] = desired_digest
    blocker_path.write_bytes(desired_payload)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="SHA-256 values are not distinct"):
        production_validator(options)(spec, report_path, work_dir)

    blocker_path.write_bytes(blocker_payload)
    report_path.write_text(json.dumps(valid_report) + "\n", encoding="utf-8")
    stale_path = blocker_path.parent / "stale-frame.cs16le"
    stale_path.write_bytes(b"stale")
    with pytest.raises(ReleaseCliError, match="directory contents differ from plan"):
        production_validator(options)(spec, report_path, work_dir)
    stale_path.unlink()

    desired_path.write_bytes(desired_payload[:-1])
    with pytest.raises(ReleaseCliError, match="on-disk byte count differs"):
        production_validator(options)(spec, report_path, work_dir)

    desired_path.write_bytes(desired_payload)
    blocker_path.write_bytes(blocker_payload[:-1] + b"X")
    with pytest.raises(ReleaseCliError, match="on-disk SHA-256 differs"):
        production_validator(options)(spec, report_path, work_dir)

    blocker_path.unlink()
    with pytest.raises(ReleaseCliError, match="raw-IQ artifact is missing"):
        production_validator(options)(spec, report_path, work_dir)


def _generated_v2_transient_fixture(
    tmp_path: Path,
    *,
    startup_hidden_transition: bool = False,
    diagnostic_overload_frame: int | None = None,
) -> tuple[ReleaseHardwareOptions, PhaseSpec, Path, Path, dict[str, Any]]:
    options = _parse(
        tmp_path,
        "--phase",
        "transient",
        "--band",
        "low=915000000",
        "--sample-rate-hz",
        "1000000",
    )
    spec = phase_specs(options)[0]
    work_dir = tmp_path / "transient-phase-work"
    quality = _base_quality(options, output_dir=work_dir, band=spec.band)

    class ReleaseFakeRadio(_FakeRadio):
        def capture_iq(
            self, buffer: object, *, metadata: bool, samples_per_channel: int
        ) -> tuple[bytes, bytes | None, int]:
            if metadata:
                return super().capture_iq(
                    buffer,
                    metadata=True,
                    samples_per_channel=samples_per_channel,
                )
            raw = _tone_raw(
                samples=samples_per_channel,
                amplitude=1_200.0,
                seed=len(self.operations),
            )
            return raw, None, 1_000 + len(self.operations)

    radio = ReleaseFakeRadio(work_dir)
    if startup_hidden_transition:
        radio.hidden_transition_capture_index = 0
    if diagnostic_overload_frame is not None:
        radio.metadata_amplitude_overrides[diagnostic_overload_frame] = 2_300.0
    radio.options.serial = options.serial
    radio.options.sample_rate_hz = quality.sample_rate_hz
    radio.options.center_frequency_hz = quality.center_frequency_hz
    radio.identity = {
        "serial": options.serial,
        "uri": "usb:1.2.3",
        "libiio_source_commit": options.libiio_source_commit,
        "context_attrs": {"fw_version": options.firmware_version},
    }
    report, report_path = _run_fake(
        radio,
        quality,
        capture=TransientCaptureOptions(),
    )
    report["cleanup"] = {
        "verified": True,
        "failures": [],
        "tx1_gain_db": -89.75,
        "tx2_gain_db": -89.75,
        "selectors": [3, 3, 3, 3],
        "dds": {
            f"altvoltage{index}": {
                "present": True,
                "scale": 0.0,
                "raw": 0.0,
            }
            for index in range(8)
        },
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return options, spec, work_dir, report_path.resolve(), report


def _tandem_mode(report: dict[str, Any]) -> dict[str, Any]:
    modes = report["modes"]
    assert isinstance(modes, list)
    return next(mode for mode in modes if mode["mode"] == MODE_TANDEM)


def _refresh_tandem_manifest_digest(tandem: dict[str, Any]) -> None:
    manifest = tandem["acquisition"]["artifact_manifest"]
    encoded = json.dumps(
        manifest["entries"],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    manifest["entries_canonical_json_sha256"] = hashlib.sha256(encoded).hexdigest()


def _refresh_tandem_projection_claim(report: dict[str, Any], work_dir: Path) -> None:
    tandem = _tandem_mode(report)
    parsed = [
        parse_tandem_frame_metadata(
            (work_dir / frame["raw_metadata_path"]).read_bytes()
        )
        for frame in tandem["batch_frames"]
    ]
    canonical = _release_canonical_tandem_evidence_bytes(tandem, parsed)
    ledger = tandem["acquisition"]["memory_ledger"]
    ledger["canonical_evidence_projection_bytes"] = len(canonical)
    ledger["canonical_evidence_projection_sha256"] = hashlib.sha256(
        canonical
    ).hexdigest()


def _rewrite_tandem_metadata_sidecar(
    report: dict[str, Any],
    work_dir: Path,
    *,
    frame_index: int,
    metadata: Any,
) -> None:
    tandem = _tandem_mode(report)
    frame = tandem["batch_frames"][frame_index]
    payload = _metadata_wire(metadata)
    parsed = parse_tandem_frame_metadata(payload)
    path = work_dir / frame["raw_metadata_path"]
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    updated = {
        "raw_metadata_bytes": len(payload),
        "raw_metadata_sha256": digest,
        "metadata": _release_tandem_metadata_dict(parsed),
    }
    frame.update(updated)
    for key in ("attack_frames", "release_frames"):
        for retained in tandem[key]:
            if retained["frame_index"] == frame_index:
                retained.update(updated)
    manifest = tandem["acquisition"]["artifact_manifest"]
    entry = manifest["entries"][frame_index]
    entry["raw_metadata_bytes"] = len(payload)
    entry["raw_metadata_sha256"] = digest
    manifest["raw_metadata_total_bytes"] = sum(
        item["raw_metadata_bytes"] for item in manifest["entries"]
    )
    _refresh_tandem_manifest_digest(tandem)


def _rewrite_tandem_temperatures(
    report: dict[str, Any],
    work_dir: Path,
    temperatures: dict[int, int | None],
) -> None:
    tandem = _tandem_mode(report)
    for frame_index, temperature in temperatures.items():
        frame = tandem["batch_frames"][frame_index]
        parsed = parse_tandem_frame_metadata(
            (work_dir / frame["raw_metadata_path"]).read_bytes()
        )
        _rewrite_tandem_metadata_sidecar(
            report,
            work_dir,
            frame_index=frame_index,
            metadata=replace(parsed, ad9361_temperature_mdeg_c=temperature),
        )
    _refresh_tandem_projection_claim(report, work_dir)


def _plant_tandem_directional_undo(
    report: dict[str, Any], work_dir: Path, *, response: str
) -> None:
    """Add one wire-valid unassigned event that undoes a commanded response."""

    tandem = _tandem_mode(report)
    frames = tandem["batch_frames"]
    parsed = [
        parse_tandem_frame_metadata(
            (work_dir / frame["raw_metadata_path"]).read_bytes()
        )
        for frame in frames
    ]
    if response == "attack":
        planted_index = 17
        direction = TandemEventDirection.INCREASE
        event_sequence = parsed[16].gain_events[-1].event_sequence + 1
    elif response == "release":
        planted_index = 41
        direction = TandemEventDirection.DECREASE
        event_sequence = parsed[40].gain_events[-1].event_sequence + 1
    else:
        raise AssertionError(f"unknown response {response!r}")

    planted_endpoint_delta = 1 if direction == TandemEventDirection.INCREASE else -1
    planted_event = TandemGainEvent(
        sample_sequence=parsed[planted_index].first_sample_sequence + 1_024,
        event_sequence=event_sequence,
        flags=int(direction) << 4,
        rx1_gain_index=(parsed[planted_index].rx1_gain_index + planted_endpoint_delta),
        rx2_gain_index=(parsed[planted_index].rx2_gain_index + planted_endpoint_delta),
    )
    for frame_index in range(planted_index, len(frames)):
        metadata = parsed[frame_index]
        gain_events = metadata.gain_events
        event_count = metadata.event_count
        transition_delta = 1
        endpoint_delta = 1 if response == "attack" else -1
        if frame_index == planted_index:
            gain_events = (planted_event,)
            event_count = 1
        elif response == "attack" and frame_index == 40:
            pre_release_decrease = TandemGainEvent(
                sample_sequence=metadata.first_sample_sequence + 1_024,
                event_sequence=event_sequence + 1,
                flags=int(TandemEventDirection.DECREASE) << 4,
                rx1_gain_index=metadata.rx1_gain_index - 1,
                rx2_gain_index=metadata.rx2_gain_index - 1,
            )
            gain_events = (
                pre_release_decrease,
                *(
                    replace(event, event_sequence=event.event_sequence + 2)
                    for event in metadata.gain_events
                ),
            )
            event_count = 2
            transition_delta = 2
            endpoint_delta = 0
        elif response == "attack" and frame_index > 40:
            transition_delta = 2
            endpoint_delta = 0
        updated = replace(
            metadata,
            event_count=event_count,
            tandem_transition_count=(
                metadata.tandem_transition_count + transition_delta
            ),
            rx1_gain_index=metadata.rx1_gain_index + endpoint_delta,
            rx2_gain_index=metadata.rx2_gain_index + endpoint_delta,
            gain_events=gain_events,
        )
        _rewrite_tandem_metadata_sidecar(
            report,
            work_dir,
            frame_index=frame_index,
            metadata=updated,
        )

    previous_transition_count: int | None = None
    for frame in frames:
        metadata = frame["metadata"]
        current_transition_count = metadata["tandem_transition_count"]
        if previous_transition_count is not None:
            frame["continuity"]["transition_count_delta"] = (
                current_transition_count - previous_transition_count
            ) % (1 << 32)
            frame["continuity"]["visible_event_count"] = len(metadata["gain_events"])
        previous_transition_count = current_transition_count
    for key in ("attack_frames", "release_frames"):
        for retained in tandem[key]:
            retained["continuity"] = json.loads(
                json.dumps(frames[retained["frame_index"]]["continuity"])
            )

    groups = tandem["partition"]["groups"]
    tandem["partition"]["stable_suffixes"] = {
        phase: _tandem_batch_stable_suffix(
            frames,
            groups[phase]["frame_indices"],
            tolerance_db=1.0,
        )
        for phase in (
            "fully_pre_attack",
            "fully_post_attack_pre_release",
            "fully_post_release",
        )
    }

    gain = tandem["gain_evidence"]
    planted_event_count = 2 if response == "attack" else 1
    gain["event_count"] += planted_event_count
    gain["unassigned_event_count"] += planted_event_count
    if response == "attack":
        gain["transitions"][1]["event"]["event_sequence"] += 2
    comparison = next(
        item for item in report["comparison"] if item["mode"] == MODE_TANDEM
    )
    comparison["gain_evidence"] = json.loads(json.dumps(gain))

    last_metadata = frames[-1]["metadata"]
    endpoint = last_metadata["bench_gain_indices"]
    transition_count = last_metadata["tandem_transition_count"]
    acquisition = tandem["acquisition"]
    for status_key in ("pre_close_tandem_status", "post_close_tandem_status"):
        acquisition[status_key].update(
            {
                "transition_count": transition_count,
                "rx1_gain_index": endpoint[0],
                "rx2_gain_index": endpoint[1],
            }
        )
    tandem["tandem_status_after"] = json.loads(
        json.dumps(acquisition["post_close_tandem_status"])
    )
    close = acquisition["close_counter_ledger"]
    close.update(
        {
            "last_frame_transition_count": transition_count,
            "pre_transition_count": transition_count,
            "post_transition_count": transition_count,
            "last_frame_to_pre_close_forward_delta": 0,
            "transition_count_forward_delta": 0,
            "pre_endpoint": endpoint,
            "post_endpoint": endpoint,
        }
    )
    _refresh_tandem_projection_claim(report, work_dir)


def _plant_schedule_candidate(
    report: dict[str, Any], *, command_id: str, after_b: bool
) -> None:
    schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][command_id]
    reads = schedule["counter_reads"]
    role = "raw_c_causal_advance" if after_b else "raw_b_first_advance"
    insert_at = next(index for index, item in enumerate(reads) if item["role"] == role)
    candidate = dict(reads[insert_at])
    candidate["role"] = "post_write_advance_candidate"
    candidate["host_after_ns"] = candidate["host_before_ns"]
    reads.insert(insert_at, candidate)
    for ordinal, item in enumerate(reads):
        item["ordinal"] = ordinal
    schedule["raw_bracket"]["post_write_read_count"] += 1


def test_runtime_generated_v2_transient_passes_production_validator(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, _report = _generated_v2_transient_fixture(
        tmp_path
    )

    validated = production_validator(options)(spec, report_path, work_dir)

    assert validated.verdict == "pass"
    assert validated.cleanup_verified is True
    assert validated.summary["mode_count"] == len(TRANSIENT_MODES)


def test_production_validator_accepts_startup_conditioning_and_diagnostic_rf(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, report = _generated_v2_transient_fixture(
        tmp_path,
        startup_hidden_transition=True,
        diagnostic_overload_frame=17,
    )
    tandem = _tandem_mode(report)
    conditioning = tandem["partition"]["pre_attack_conditioning"]
    policy = tandem["partition"]["rf_quality_policy"]

    assert conditioning["startup_initial_unrepresented_transition_count"] == 1
    assert conditioning["startup_is_conditioning_only"] is True
    assert conditioning["startup_is_response_direction_proof"] is False
    assert tandem["batch_frames"][17]["analysis"]["quality_valid"] is False
    assert 17 in policy["diagnostic_frame_indices"]
    assert 17 not in policy["strict_frame_indices"]
    assert policy["diagnostic_windows_authorize_pass"] is False

    validated = production_validator(options)(spec, report_path, work_dir)

    assert validated.verdict == "pass"
    assert validated.cleanup_verified is True


def test_production_validator_accepts_only_leading_temperature_omissions(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, report = _generated_v2_transient_fixture(
        tmp_path / "leading-temperature-omission"
    )
    _rewrite_tandem_temperatures(report, work_dir, {0: None, 1: None})
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    validated = production_validator(options)(spec, report_path, work_dir)

    assert validated.cleanup_verified is True


@pytest.mark.parametrize(
    "temperatures",
    (
        {2: None},
        {index: None for index in range(64)},
        {0: 125_001},
        {0: -40_001},
    ),
)
def test_production_validator_rejects_invalid_temperature_sessions(
    tmp_path: Path, temperatures: dict[int, int | None]
) -> None:
    options, spec, work_dir, report_path, report = _generated_v2_transient_fixture(
        tmp_path / f"invalid-temperature-{len(temperatures)}-{next(iter(temperatures))}"
    )
    _rewrite_tandem_temperatures(report, work_dir, temperatures)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseCliError):
        production_validator(options)(spec, report_path, work_dir)


def test_release_validator_recomputes_whole_window_stable_suffix(
    tmp_path: Path,
) -> None:
    _options, _spec, _work_dir, _report_path, report = _generated_v2_transient_fixture(
        tmp_path
    )
    tandem = _tandem_mode(report)
    frames = tandem["batch_frames"]
    partition = tandem["partition"]
    assert isinstance(frames, list)
    assert isinstance(partition, dict)
    indices = partition["groups"]["fully_post_release"]["frame_indices"]
    for frame_index in indices[-8:]:
        windows = frames[frame_index]["analysis"]["windows"]
        for window_index, window in enumerate(windows):
            level = -20.0 if window_index % 2 == 0 else -40.0
            window["tone_dbfs"] = [level, level]

    with pytest.raises(ValueError, match="exceeds its RF tolerance"):
        _tandem_batch_stable_suffix(frames, indices, tolerance_db=1.0)


def test_release_validator_recomputes_startup_conditioning_and_quiet_suffix(
    tmp_path: Path,
) -> None:
    radio = _FakeRadio(tmp_path)
    radio.planted_suffix_event_capture_index = 0
    report, _path = _run_fake(radio, _quality(tmp_path))
    tandem = _tandem_mode(report)
    frames = tandem["batch_frames"]
    pre_indices = tandem["partition"]["groups"]["fully_pre_attack"]["frame_indices"]

    recomputed = _tandem_batch_pre_attack_conditioning(frames, pre_indices)

    assert recomputed == tandem["partition"]["pre_attack_conditioning"]
    assert recomputed["startup_transition_count"] == 1
    assert recomputed["startup_is_response_direction_proof"] is False
    frames[pre_indices[-1]]["continuity"]["transition_count_delta"] = 1
    with pytest.raises(ValueError, match="quiet suffix contains a transition"):
        _tandem_batch_pre_attack_conditioning(frames, pre_indices)


def test_release_validator_recomputes_transient_rf_quality_policy(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, report = _generated_v2_transient_fixture(
        tmp_path
    )
    policy = _tandem_mode(report)["partition"]["rf_quality_policy"]
    policy["diagnostic_windows_authorize_pass"] = True
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    with pytest.raises(
        ReleaseCliError,
        match="five-way partition differs from recomputation",
    ):
        production_validator(options)(spec, report_path, work_dir)


@pytest.mark.parametrize("response", ("attack", "release"))
def test_production_validator_rejects_self_consistent_directional_undo(
    tmp_path: Path, response: str
) -> None:
    options, spec, work_dir, report_path, report = _generated_v2_transient_fixture(
        tmp_path
    )
    _plant_tandem_directional_undo(report, work_dir, response=response)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseCliError) as raised:
        production_validator(options)(spec, report_path, work_dir)
    assert str(raised.value) == (
        "transient tandem stable endpoints do not prove the commanded "
        "attack decrease and release increase"
    )


def test_production_validator_rejects_planted_v2_contract_mutations(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, valid_report = (
        _generated_v2_transient_fixture(tmp_path)
    )
    validate = production_validator(options)

    def target(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        acquisition = tandem["acquisition"]
        planted = (acquisition["targets"]["strong_attack"]["target_raw"] + 1) % (
            1 << 32
        )
        acquisition["targets"]["strong_attack"]["target_raw"] = planted
        acquisition["schedule_diagnostics"]["strong_attack"]["target"]["target_raw"] = (
            planted
        )
        acquisition["schedule_plan"]["commands"][0]["target_raw"] = planted

    def frozen_chronology(report: dict[str, Any]) -> None:
        plan = _tandem_mode(report)["acquisition"]["schedule_plan"]
        plan["targets_frozen_host_ns"] = plan["worker_start_requested_ns"] + 1

    def worker_start_chronology(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        plan = tandem["acquisition"]["schedule_plan"]
        attack = tandem["commands"][1]
        plan["worker_start_returned_ns"] = attack["host_after_ns"] + 1

    def tx1_pre_chronology(report: dict[str, Any]) -> None:
        schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "strong_attack"
        ]
        raw_a = next(
            item
            for item in schedule["counter_reads"]
            if item["role"] == "raw_a_prewrite"
        )
        schedule["tx1_mute_assurance"]["pre"].update(
            {
                "host_before_ns": raw_a["host_after_ns"],
                "host_after_ns": raw_a["host_after_ns"],
            }
        )

    def refill_completion(report: dict[str, Any]) -> None:
        acquisition = _tandem_mode(report)["acquisition"]
        acquisition["initiating_refill_completion_monotonic_ns"] += 12_345

    def shutdown_chronology(report: dict[str, Any]) -> None:
        events = _tandem_mode(report)["acquisition"]["shutdown"]["events"]
        for index, event in enumerate(events):
            event["monotonic_ns"] = index

    def readback(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        acquisition = tandem["acquisition"]
        schedule = acquisition["schedule_diagnostics"]["weak_release"]
        command = tandem["commands"][2]
        unbound = acquisition["unbound_commands"]["weak_release"]
        observed = command["requested_level_db"] + 0.5
        schedule["deferred_tx2_readback"].update(
            {"observed_level_db": observed, "passed": False}
        )
        schedule["applied_level_db"] = observed
        command["applied_level_db"] = observed
        unbound["applied_level_db"] = observed
        effective = report["safety"]["physical_attenuation_db"] - observed
        command["effective_attenuation_db"] = effective
        unbound["effective_attenuation_db"] = effective

    def tx1(report: dict[str, Any]) -> None:
        assurance = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "strong_attack"
        ]["tx1_mute_assurance"]["post"]
        assurance.update({"observed_level_db": -70.0, "passed": False})

    def malformed_post_count(report: dict[str, Any]) -> None:
        schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "strong_attack"
        ]
        schedule["raw_bracket"]["post_write_read_count"] = "3"

    def malformed_counter_read(report: dict[str, Any]) -> None:
        schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "weak_release"
        ]
        schedule["counter_reads"][-1] = None

    def malformed_poll_observation(report: dict[str, Any]) -> None:
        schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "strong_attack"
        ]
        schedule["target"]["poll_observations"][-2] = None

    def cache(report: dict[str, Any]) -> None:
        acquisition = _tandem_mode(report)["acquisition"]
        acquisition["configured_batch_cache_bytes"] += 1

    def refill(report: dict[str, Any]) -> None:
        acquisition = _tandem_mode(report)["acquisition"]
        acquisition["cached_replay_refill_calls"] = 62

    def measured_memory(report: dict[str, Any]) -> None:
        ledger = _tandem_mode(report)["acquisition"]["memory_ledger"]
        ledger["measured_finished_mode_and_parsed_metadata_bytes"] = 1

    def canonical_bytes(report: dict[str, Any]) -> None:
        ledger = _tandem_mode(report)["acquisition"]["memory_ledger"]
        ledger["canonical_evidence_projection_bytes"] += 1

    def canonical_sha(report: dict[str, Any]) -> None:
        ledger = _tandem_mode(report)["acquisition"]["memory_ledger"]
        ledger["canonical_evidence_projection_sha256"] = "0" * 64

    def canonical_method(report: dict[str, Any]) -> None:
        ledger = _tandem_mode(report)["acquisition"]["memory_ledger"]
        ledger["canonical_evidence_projection_method"] += ":planted"

    def canonicalized_target(report: dict[str, Any]) -> None:
        target(report)
        _refresh_tandem_projection_claim(report, work_dir)

    def phase_memory(report: dict[str, Any]) -> None:
        ledger = _tandem_mode(report)["acquisition"]["memory_ledger"]
        ledger["post_close_fft_workspace_bytes"] = 4_194_304
        ledger["post_close_materialization_envelope_bytes"] -= 4_194_304

    def partition(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        tandem["partition"]["phase_by_frame"][0] = "attack_bracket"
        tandem["batch_frames"][0]["batch_phase"] = "attack_bracket"

    def quality(report: dict[str, Any]) -> None:
        window = _tandem_mode(report)["batch_frames"][0]["analysis"]["windows"][0]
        window["quality_valid"] = False
        window["quality_reasons"] = ["planted_invalid_window"]

    def frame_unknown_field(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["fatal_error"] = (
            "planted preserved failure"
        )

    def analysis_unknown_field(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["analysis"]["fatal_error"] = (
            "planted preserved failure"
        )

    def continuity_unknown_field(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["continuity"]["fatal_error"] = (
            "planted preserved failure"
        )

    def metadata_unknown_field(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["metadata"]["fatal_error"] = (
            "planted preserved failure"
        )

    def metadata_numeric_type(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["metadata"]["version"] = 5.0

    def analysis_numeric_type(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["analysis"]["windows"][0][
            "window_index"
        ] = 0.0

    def malformed_final_event(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        frame = next(
            frame
            for frame in tandem["batch_frames"]
            if frame["metadata"]["gain_events"]
        )
        frame["metadata"]["gain_events"][-1] = None

    def malformed_frame_index(report: dict[str, Any]) -> None:
        _tandem_mode(report)["batch_frames"][0]["frame_index"] = "bad"

    def escaped_anchor_path(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        anchor_index = tandem["conditioning_anchor"]["source"]["source_frame_index"]
        tandem["batch_frames"][anchor_index]["iq_path"] = "/dev/zero"

    def escaped_release_anchor_path(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        release_source = tandem["response_observations"]["release"]["baseline_anchor"]
        tandem["batch_frames"][release_source["source_frame_index"]]["iq_path"] = (
            "../../outside"
        )

    def gain(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        tandem["gain_evidence"]["evidence_valid"] = False
        comparison = next(
            item for item in report["comparison"] if item["mode"] == MODE_TANDEM
        )
        comparison["gain_evidence"] = tandem["gain_evidence"]

    def response(report: dict[str, Any]) -> None:
        _tandem_mode(report)["responses"]["attack"]["evidence_valid"] = False

    def close_counter(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        acquisition = tandem["acquisition"]
        ledger = acquisition["close_counter_ledger"]
        post = (ledger["pre_transition_count"] + 65) % (1 << 32)
        ledger["post_transition_count"] = post
        ledger["transition_count_forward_delta"] = 65
        acquisition["post_close_tandem_status"]["transition_count"] = post
        tandem["tandem_status_after"]["transition_count"] = post

    def cancel(report: dict[str, Any]) -> None:
        shutdown = _tandem_mode(report)["acquisition"]["shutdown"]
        shutdown.update(
            {
                "cancel_required": True,
                "cancel_called": True,
                "cancel_succeeded": True,
                "shutdown_path": "cancel_after_full_cache_replay",
            }
        )

    def status(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        acquisition = tandem["acquisition"]
        acquisition["post_close_tandem_status"]["fifo_level"] = 1
        acquisition["close_counter_ledger"]["post_fifo_level"] = 1
        tandem["tandem_status_after"]["fifo_level"] = 1

    def configuration(report: dict[str, Any]) -> None:
        report["configuration"]["tandem_transport"]["queue_capacity_frames"] = 3
        _tandem_mode(report)["acquisition"]["queue_capacity_frames"] = 3
        report["evidence_policy"]["tandem_capture_queue_frames"] = 3

    def evidence_policy(report: dict[str, Any]) -> None:
        report["evidence_policy"]["tandem_aggregate_resident_bytes"] -= 1

    def metadata_request(report: dict[str, Any]) -> None:
        _tandem_mode(report)["metadata_request"]["decoded"]["initial_gain_db"] = 61

    def artifact_completion(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        frame = tandem["batch_frames"][0]
        frame["artifact_write_status"]["iq_write_completed"] = False
        manifest = tandem["acquisition"]["artifact_manifest"]
        manifest["entries"][0]["write_status"]["iq_write_completed"] = False
        manifest["completed_iq_files"] = 63
        manifest["write_complete"] = False
        _refresh_tandem_manifest_digest(tandem)

    def malformed_modes(report: dict[str, Any]) -> None:
        report["modes"] = [None]

    def malformed_comparison(report: dict[str, Any]) -> None:
        report["comparison"] = [None]

    def contradictory_failure(report: dict[str, Any]) -> None:
        report["failure_evidence"] = _tandem_mode(report)

    def fatal_error(report: dict[str, Any]) -> None:
        report["fatal_error"] = "planted contradictory PASS error"

    def cleanup_request_error(report: dict[str, Any]) -> None:
        report["cleanup_request_error"] = "planted contradictory cleanup error"

    def bench_mapping(report: dict[str, Any]) -> None:
        report["bench_port_mapping"]["stimulus"] = "bench TX1"

    def cleanup_unknown_field(report: dict[str, Any]) -> None:
        report["cleanup"]["fatal_error"] = "planted preserved failure"

    def final_rx_state_unknown_field(report: dict[str, Any]) -> None:
        _tandem_mode(report)["final_rx_state"]["fatal_error"] = (
            "planted restore failure"
        )

    def ordinary_initial_rx_state(report: dict[str, Any]) -> None:
        mode = next(
            item for item in report["modes"] if item["mode"] == "native_fast_attack"
        )
        initial = mode["commands"][0]
        initial["rx_state_before"]["modes"] = ["fast_attack", "fast_attack"]

    mutations = [
        ("frozen target", target),
        ("pre-start chronology", frozen_chronology),
        ("worker-start chronology", worker_start_chronology),
        ("TX1-pre chronology", tx1_pre_chronology),
        ("initiating refill completion", refill_completion),
        ("shutdown chronology", shutdown_chronology),
        (
            "candidate before B",
            lambda report: _plant_schedule_candidate(
                report, command_id="strong_attack", after_b=False
            ),
        ),
        (
            "candidate after B",
            lambda report: _plant_schedule_candidate(
                report, command_id="weak_release", after_b=True
            ),
        ),
        ("deferred readback", readback),
        ("TX1 attestation", tx1),
        ("malformed post-write count", malformed_post_count),
        ("malformed counter read", malformed_counter_read),
        ("malformed poll observation", malformed_poll_observation),
        ("batch cache", cache),
        ("full replay", refill),
        ("claimed memory", measured_memory),
        ("canonical bytes", canonical_bytes),
        ("canonical SHA", canonical_sha),
        ("canonical method", canonical_method),
        ("self-consistent canonical target", canonicalized_target),
        ("phase memory", phase_memory),
        ("partition", partition),
        ("window quality", quality),
        ("frame unknown field", frame_unknown_field),
        ("analysis unknown field", analysis_unknown_field),
        ("continuity unknown field", continuity_unknown_field),
        ("metadata unknown field", metadata_unknown_field),
        ("metadata numeric type", metadata_numeric_type),
        ("analysis numeric type", analysis_numeric_type),
        ("malformed final event", malformed_final_event),
        ("malformed frame index", malformed_frame_index),
        ("escaped anchor path", escaped_anchor_path),
        ("escaped release anchor path", escaped_release_anchor_path),
        ("gain evidence", gain),
        ("response evidence", response),
        ("close counter", close_counter),
        ("successful cancel", cancel),
        ("post-close status", status),
        ("transport configuration", configuration),
        ("evidence policy", evidence_policy),
        ("metadata request", metadata_request),
        ("artifact completion", artifact_completion),
        ("malformed modes", malformed_modes),
        ("malformed comparison", malformed_comparison),
        ("contradictory failure evidence", contradictory_failure),
        ("failure-only fatal error", fatal_error),
        ("failure-only cleanup error", cleanup_request_error),
        ("bench mapping", bench_mapping),
        ("cleanup unknown field", cleanup_unknown_field),
        ("final RX state unknown field", final_rx_state_unknown_field),
        ("ordinary initial RX state", ordinary_initial_rx_state),
    ]
    for label, mutate in mutations:
        planted = json.loads(json.dumps(valid_report))
        mutate(planted)
        if label not in {
            "canonical bytes",
            "canonical SHA",
            "malformed modes",
        }:
            _refresh_tandem_projection_claim(planted, work_dir)
        report_path.write_text(json.dumps(planted) + "\n", encoding="utf-8")
        try:
            validate(spec, report_path, work_dir)
        except ReleaseCliError:
            pass
        else:
            pytest.fail(f"planted {label} mutation was accepted")


def test_production_validator_stats_exact_sidecar_sizes_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    options, spec, work_dir, report_path, valid_report = (
        _generated_v2_transient_fixture(tmp_path)
    )
    frame = _tandem_mode(valid_report)["batch_frames"][0]
    paths = {
        (work_dir / frame["iq_path"]).resolve(),
        (work_dir / frame["raw_metadata_path"]).resolve(),
    }
    for path in paths:
        path.write_bytes(path.read_bytes() + b"\x00")

    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path.resolve() in paths:
            raise AssertionError("oversized sidecar was read before its size gate")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    with pytest.raises(ReleaseCliError):
        production_validator(options)(spec, report_path, work_dir)


def test_production_validator_reparses_self_consistent_metadata_physics_mutations(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, valid_report = (
        _generated_v2_transient_fixture(tmp_path)
    )
    validate = production_validator(options)
    frame_index = 18
    valid_frame = _tandem_mode(valid_report)["batch_frames"][frame_index]
    metadata_path = work_dir / valid_frame["raw_metadata_path"]
    original_payload = metadata_path.read_bytes()
    original = parse_tandem_frame_metadata(original_payload)

    prior_events = [
        event
        for frame in _tandem_mode(valid_report)["batch_frames"][:frame_index]
        for event in frame["metadata"]["gain_events"]
    ]
    first_event_sequence = (
        (prior_events[-1]["event_sequence"] + 1) % (1 << 32) if prior_events else 1
    )

    def events(count: int, *, spacing: int) -> tuple[TandemGainEvent, ...]:
        endpoint = original.rx1_gain_index
        planted: list[TandemGainEvent] = []
        for index in range(count):
            direction = (
                TandemEventDirection.DECREASE
                if index % 2 == 0
                else TandemEventDirection.INCREASE
            )
            endpoint += -1 if direction == TandemEventDirection.DECREASE else 1
            planted.append(
                TandemGainEvent(
                    sample_sequence=(
                        original.first_sample_sequence + 1_024 + index * spacing
                    ),
                    event_sequence=(first_event_sequence + index) % (1 << 32),
                    flags=int(direction) << 4,
                    rx1_gain_index=endpoint,
                    rx2_gain_index=endpoint,
                )
            )
        return tuple(planted)

    five_events = events(5, spacing=10_000)
    too_close_events = events(2, spacing=1)
    mutations = (
        ("six observations", replace(original, observation_count=6)),
        (
            "five visible events",
            replace(
                original,
                event_count=5,
                tandem_transition_count=original.tandem_transition_count + 5,
                rx1_gain_index=five_events[-1].rx1_gain_index,
                rx2_gain_index=five_events[-1].rx2_gain_index,
                gain_events=five_events,
            ),
        ),
        (
            "too-close events",
            replace(
                original,
                event_count=2,
                tandem_transition_count=original.tandem_transition_count + 2,
                rx1_gain_index=too_close_events[-1].rx1_gain_index,
                rx2_gain_index=too_close_events[-1].rx2_gain_index,
                gain_events=too_close_events,
            ),
        ),
    )
    for label, metadata in mutations:
        planted = json.loads(json.dumps(valid_report))
        _rewrite_tandem_metadata_sidecar(
            planted,
            work_dir,
            frame_index=frame_index,
            metadata=metadata,
        )
        _refresh_tandem_projection_claim(planted, work_dir)
        report_path.write_text(json.dumps(planted) + "\n", encoding="utf-8")
        try:
            validate(spec, report_path, work_dir)
        except ReleaseCliError:
            pass
        else:
            pytest.fail(f"planted {label} mutation was accepted")
        metadata_path.write_bytes(original_payload)


def test_production_validator_rejects_nonfinite_and_overflowed_json_numbers(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, valid_report = (
        _generated_v2_transient_fixture(tmp_path)
    )
    validate = production_validator(options)
    planted = json.loads(json.dumps(valid_report))
    _tandem_mode(planted)["batch_frames"][0]["iq_bytes"] = float("nan")
    report_path.write_text(json.dumps(planted) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCliError, match="strict finite JSON"):
        validate(spec, report_path, work_dir)

    encoded = json.dumps(valid_report)
    assert '"iq_bytes": 524288' in encoded
    report_path.write_text(
        encoded.replace('"iq_bytes": 524288', '"iq_bytes": 1e999', 1) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ReleaseCliError, match="strict finite JSON"):
        validate(spec, report_path, work_dir)


def test_production_validator_rejects_float_overflowing_json_integers_cleanly(
    tmp_path: Path,
) -> None:
    options, spec, work_dir, report_path, valid_report = (
        _generated_v2_transient_fixture(tmp_path)
    )
    validate = production_validator(options)
    huge = 10**4000

    def elapsed(report: dict[str, Any]) -> None:
        report["elapsed_seconds"] = huge

    def cleanup_gain(report: dict[str, Any]) -> None:
        report["cleanup"]["tx1_gain_db"] = huge

    def ordinary_final_gain(report: dict[str, Any]) -> None:
        ordinary = next(mode for mode in report["modes"] if mode["mode"] != MODE_TANDEM)
        ordinary["final_rx_state"]["gains_db"][0] = huge

    def ordinary_analysis(report: dict[str, Any]) -> None:
        ordinary = next(mode for mode in report["modes"] if mode["mode"] != MODE_TANDEM)
        ordinary["baseline_frames"][0]["analysis"]["selected_tone_hz"] = huge

    def tandem_suffix(report: dict[str, Any]) -> None:
        tandem = _tandem_mode(report)
        indices = tandem["partition"]["groups"]["fully_post_release"]["frame_indices"]
        tandem["batch_frames"][indices[-1]]["analysis"]["windows"][0]["tone_dbfs"][
            0
        ] = huge

    def tandem_readback(report: dict[str, Any]) -> None:
        schedule = _tandem_mode(report)["acquisition"]["schedule_diagnostics"][
            "strong_attack"
        ]
        schedule["deferred_tx2_readback"]["observed_level_db"] = huge

    mutations = (
        ("elapsed", elapsed, False),
        ("cleanup gain", cleanup_gain, False),
        ("ordinary final gain", ordinary_final_gain, False),
        ("ordinary analysis", ordinary_analysis, False),
        ("tandem suffix", tandem_suffix, True),
        ("tandem readback", tandem_readback, True),
    )
    for label, mutate, refresh_projection in mutations:
        planted = json.loads(json.dumps(valid_report))
        mutate(planted)
        if refresh_projection:
            _refresh_tandem_projection_claim(planted, work_dir)
        report_path.write_text(json.dumps(planted) + "\n", encoding="utf-8")
        try:
            validate(spec, report_path, work_dir)
        except ReleaseCliError:
            pass
        else:
            pytest.fail(f"float-overflowing {label} JSON integer was accepted")


def test_baseline_soak_requires_temperature_evidence(tmp_path: Path) -> None:
    soak = _parse(
        tmp_path,
        "--phase",
        "steady",
        "--policy-set",
        "baseline",
    )
    records = {
        "run-a": {
            "status": "complete",
            "summary": {"temperature": {"available": False, "count": 0}},
        }
    }

    assert _soak_temperature_errors(soak, records) == [
        "baseline soak run run-a lacks temperature evidence"
    ]
    records["run-a"]["summary"]["temperature"] = {
        "available": True,
        "count": 3,
        "median_c": 35.0,
    }
    assert _soak_temperature_errors(soak, records) == []
