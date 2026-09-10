"""Offline high-rate cohort qualification; no RTL or public guard changes."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from tests.starlink_oracle import high_rate_paired as oracle
from tests.starlink_oracle import xfft_bitacc
from tests.starlink_oracle.ddc import _round_shift_q15, x2_ddc_ci16
from tests.starlink_oracle.fixed import fixed_correlate_ci16
from tests.starlink_oracle.pilot_ddc import PilotDdcOracle, _round_saturate
from tools.generate_starlink_periodic_map_vectors import unpack


@pytest.fixture(scope="module")
def cohort(tmp_path_factory):
    parent = tmp_path_factory.mktemp("high-rate-cohort")
    output = parent / "cohort"
    info = oracle.generate(output)
    return output, info


@pytest.mark.parametrize("field", sorted(oracle.CONTRACT))
def test_every_contract_field_mutant_rejected(field):
    value = copy.deepcopy(oracle.CONTRACT)
    original = value[field]
    value[field] = original + 1 if type(original) is int else "mutant"
    with pytest.raises(ValueError, match="unadmitted"):
        oracle.require_contract(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_rate_msps", 30.0),
        ("decimation", True),
        ("source_rate_msps", 60),
        ("edge", "lower"),
        ("native_taps", 66),
        ("native_qualified_lags", [-30, 30]),
    ],
)
def test_no_implicit_rate_or_native66_alias(field, value):
    contract = dict(oracle.CONTRACT, **{field: value})
    with pytest.raises(ValueError):
        oracle.require_contract(contract)


def test_exact_support_and_native_scaled_profile():
    first, end = oracle.raw_support(oracle.PRE_FIRST, 4096)
    assert first == oracle.RAW_FIRST and end - first == 8205
    assert first % 2 == 1
    assert oracle.raw_support(oracle.PRE_FIRST, 768)[1] - first == 1549
    assert (
        oracle.raw_support(oracle.FIRST, 959)[1]
        - oracle.raw_support(oracle.FIRST, 959)[0]
        == 1931
    )
    assert oracle.CENTER - oracle.RAW_FIRST == 2583
    assert oracle.admission_lead(2 * oracle.FIRST + 256) == 719


@pytest.mark.parametrize(
    "count,phase", [(8192, 0), (8204, 0), (8206, 0), (8205, 1), (8205, -1)]
)
def test_wrong_halo_or_phase_rejected(count, phase):
    source, _ = oracle.source_fixture()
    with pytest.raises(ValueError, match="halo/phase"):
        oracle.conditioner_trace(
            np.resize(source, (count, 2)), oracle.RAW_FIRST + phase
        )


def test_missing_halo_changes_real_ddc_support():
    source, _ = oracle.source_fixture()
    missing = x2_ddc_ci16(source[1:], first_input_index=oracle.RAW_FIRST + 1)
    assert len(missing.samples_iq) == 4095
    assert missing.output_indexes[0] == oracle.PRE_FIRST + 1


@pytest.mark.parametrize(
    "n",
    [
        -(1 << 31),
        -1073758208,
        -49152,
        -16384,
        -1,
        0,
        1,
        16384,
        49152,
        1073709056,
        1073725440,
        (1 << 31) - 1,
    ],
)
def test_ddc_rounding_clipping_boundaries(n):
    output, count = oracle.rounded_ci16(np.array([[n, -n]], dtype=np.int64), 15)
    a, sa = _round_shift_q15(n)
    b, sb = _round_shift_q15(-n)
    assert output.tolist() == [[a, b]] and count == sa + sb


@pytest.mark.parametrize("shift", [16, 17])
def test_pilot_signed_ties_and_saturation_boundaries(shift):
    values = np.array(
        [
            [
                k * (1 << shift) + (1 << (shift - 1)),
                -k * (1 << shift) - (1 << (shift - 1)),
            ]
            for k in [0, 1, 2, 32766, 32767, 32768]
        ],
        dtype=np.int64,
    )
    actual, clips = oracle.rounded_ci16(values, shift)
    expected, expected_clips = _round_saturate(values, shift)
    assert np.array_equal(actual, expected) and clips == expected_clips


def test_native_actual_hardware_bounds_not_66tap(cohort):
    source, native = oracle.source_fixture()
    row = fixed_correlate_ci16(source[2583 : 2583 + 132], native)
    assert row.tap_count == 132 and oracle.tuple_legal(row)
    for kwargs in (
        {"tap_count": 66},
        {"sample_energy": 0},
        {"sample_energy": 1 << 38},
        {"coefficient_energy": 0},
        {"coefficient_energy": 1 << 31},
        {"saturation_events": 1},
        {"real": 1 << 38},
        {"imag": -(1 << 38) - 1},
    ):
        assert not oracle.tuple_legal(replace(row, **kwargs))
    # These check the RTL predicate only, not arithmetic qualification at its
    # extreme values. Real cohort maxima are independently reported below it.
    assert oracle.tuple_legal(
        replace(
            row,
            real=-(1 << 38),
            imag=(1 << 38) - 1,
            sample_energy=(1 << 38) - 1,
            coefficient_energy=(1 << 31) - 1,
        )
    )


def test_lead_boundary_uses_next_sample():
    start = oracle.CENTER - 64
    assert oracle.admission_lead(start - 129) == 128
    with pytest.raises(ValueError, match="late"):
        oracle.admission_lead(start - 128)
    for current in (-1, True, (1 << 64) - 1):
        with pytest.raises(ValueError):
            oracle.admission_lead(current)


def test_full_cohort_rederived_and_original_width_unchanged(cohort):
    output, receipt = cohort
    assert xfft_bitacc.XFFT_DATA_BITS == 24 and xfft_bitacc.XFFT_FRACTION_BITS == 23
    assert oracle.verify(output) == receipt
    assert xfft_bitacc.XFFT_DATA_BITS == 24 and xfft_bitacc.XFFT_FRACTION_BITS == 23
    assert receipt["coarse"]["words_per_stage"] == 3584
    assert receipt["coarse"]["scores"] == 3129
    assert receipt["native"]["qualified"] == 121 and receipt["native"]["raw"] == 129
    assert receipt["native"]["planned_lead_at_latest_accept"] == 719
    assert receipt["pilot"]["supported_selected"] == 512
    assert receipt["pilot"]["unsupported_before_first"] == 90
    assert (
        receipt["ddc"]["accepted"] == 8205 and receipt["ddc"]["saturation_events"] == 0
    )
    assert (
        output / "conditioned_kernel_q17.mem"
    ).read_bytes() == oracle.KERNEL.read_bytes()
    assert oracle.digest(oracle.KERNEL.read_bytes()) == oracle.KERNEL_SHA


def test_all_maps_and_support_from_independent_sequential_accumulation(cohort):
    output, receipt = cohort
    scores = oracle.read_mem((output / "scores_u8.mem").read_bytes(), 3129, 2)
    for bins in (343, 447):
        accumulator = [0] * bins
        for p, score in enumerate(scores[: 2 * bins]):
            accumulator[p % bins] += score
        assert (
            oracle.read_mem((output / f"map_{bins}x2_u16.mem").read_bytes(), bins, 4)
            == accumulator
        )
    assert receipt["coarse"]["all_blocks_canonical_support"] == [
        oracle.FIRST,
        oracle.FIRST + 3194,
    ]
    assert receipt["coarse"]["remaining_canonical_after_last_complete_block"] == 134


def test_all_fft_input_words_indexes_and_zero_wire_padding(cohort):
    output, _ = cohort
    source = unpack(
        oracle.read_mem((output / "canonical_ci16.mem").read_bytes(), 4096, 8), 16
    )
    q17 = oracle.read_mem((output / "fft_input_q17.mem").read_bytes(), 3584, 9)
    axi = oracle.read_mem((output / "fft_input_axi48.mem").read_bytes(), 3584, 12)
    indexes = oracle.read_mem(
        (output / "fft_input_index_u64.mem").read_bytes(), 3584, 16
    )
    positions = oracle.read_mem((output / "fft_position_u9.mem").read_bytes(), 3584, 3)
    for row in range(3584):
        block, position = divmod(row, 512)
        i, q = source[768 + block * 447 + position].astype(np.int64) * 4
        assert q17[row] == ((int(q) & 0x3FFFF) << 18) | (int(i) & 0x3FFFF)
        assert axi[row] == ((int(q) & 0x3FFFF) << 24) | (int(i) & 0x3FFFF)
        assert axi[row] & 0xFC0000FC0000 == 0
        assert indexes[row] == oracle.FIRST + block * 447 + position
        assert positions[row] == position


@pytest.mark.parametrize(
    "wrong", ["upper_edge_pss_kernel_q17.mem", "upper_edge_pss60_x4_ddc_kernel_q17.mem"]
)
def test_wrong_rate_kernel_cannot_be_substituted(tmp_path, monkeypatch, wrong):
    model_dir = oracle.prepare_installed_cmodel(tmp_path)
    monkeypatch.setattr(oracle, "KERNEL", oracle.ACQ / "tb" / wrong)
    with (
        oracle.Model18(model_dir) as model,
        pytest.raises(ArithmeticError, match="kernel must byte-match"),
    ):
        oracle.conditioned_kernel(model)


def test_pilot_chunk_invariance_and_absolute_support(cohort):
    output, receipt = cohort
    canonical = unpack(
        oracle.read_mem((output / "canonical_ci16.mem").read_bytes(), 4096, 8), 16
    )
    instance = PilotDdcOracle("upper")
    pieces = []
    for begin, end in [(0, 767), (767, 768), (768, 1731), (1731, 4096)]:
        pieces.append(
            instance.process(canonical[begin:end], first_index=oracle.PRE_FIRST + begin)
        )
    output_iq = np.concatenate([p.samples_iq for p in pieces])
    valid = np.concatenate([p.support_valid for p in pieces])
    assert (
        output_iq[valid][:512].astype("<i2").tobytes()
        == (output / "pilot_expected.ci16").read_bytes()
    )
    pilot = receipt["pilot"]
    first, last = pilot["first_newest_canonical"], pilot["last_newest_canonical"]
    assert first % 6 == last % 6 == 0 and last - first == 511 * 6
    assert pilot["raw_support_half_open"] == [2 * (first - 538) - 7, 2 * last + 8]
    assert pilot["raw_centers"] == [2 * (first - 269), 2 * (last - 269)]


def test_source_nonperiodic_and_native_packet_on_original_raw(cohort):
    output, receipt = cohort
    raw = unpack(
        oracle.read_mem((output / "source_ci16.mem").read_bytes(), 8205, 8), 16
    )
    source, native = oracle.source_fixture()
    assert np.array_equal(raw, source)
    assert not np.array_equal(source[:447], source[447:894])
    assert np.array_equal(source[2583:2715], native)
    packet = oracle.read_mem(
        (output / "native_expected_packet.mem").read_bytes(), 26, 8
    )
    assert packet[0:3] == [0x31535350, 0x1A010001, oracle.REQUEST]
    assert packet[3] + (packet[4] << 32) == oracle.CENTER
    assert packet[7] == 0 and packet[10] == oracle.GENERATION
    rows = json.loads((output / "native_all_raw_tuples.json").read_bytes())
    assert len(rows) == 129 and sum(r["qualified"] for r in rows) == 121
    assert all(r["tap_count"] == 132 for r in rows)
    assert receipt["native"]["winner_lag"] == 0


@pytest.mark.parametrize(
    "name",
    [
        "source_ci16.mem",
        "canonical_ci16.mem",
        "conditioned_kernel_q17.mem",
        "forward_q17.mem",
        "product_q17.mem",
        "inverse_q17.mem",
        "scores_u8.mem",
        "native_expected_packet.mem",
        "native_real_s48.mem",
        "pilot_expected.ci16",
    ],
)
def test_self_rehashed_numeric_mutants_cannot_become_goldens(cohort, name):
    output, _ = cohort
    target, manifest = output / name, output / "cohort.json"
    original, original_manifest = target.read_bytes(), manifest.read_bytes()
    modified = bytearray(original)
    modified[0] = ord("1") if modified[0] != ord("1") else ord("0")
    record = json.loads(original_manifest)
    record["files"][name]["sha256"] = oracle.digest(modified)
    try:
        target.write_bytes(modified)
        manifest.write_bytes(oracle.json_bytes(record))
        with pytest.raises(ValueError, match="recomputation"):
            oracle.verify(output)
    finally:
        target.write_bytes(original)
        manifest.write_bytes(original_manifest)


def test_lane_swap_and_truncated_source_cannot_replace_cohort(cohort):
    output, _ = cohort
    path = output / "source_ci16.mem"
    original = path.read_bytes()
    words = oracle.read_mem(original, 8205, 8)
    for payload in (
        oracle.mem([((w & 65535) << 16) | (w >> 16) for w in words], 8),
        original[:-9],
    ):
        try:
            path.write_bytes(payload)
            with pytest.raises(ValueError, match="golden mismatch"):
                oracle.verify(output)
        finally:
            path.write_bytes(original)


def test_frozen_source_snapshot_and_extra_file_rejected(cohort):
    output, receipt = cohort
    path = output / "source_snapshot" / next(iter(receipt["source_sha256"]))
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n")
        with pytest.raises(ValueError, match="source snapshot hash"):
            oracle.verify(output)
    finally:
        path.write_bytes(original)
    extra = output / "unreviewed"
    try:
        extra.write_bytes(b"extra")
        with pytest.raises(ValueError, match="unexpected"):
            oracle.verify(output)
    finally:
        extra.unlink()


def test_absent_only_and_unsupported_cohort(cohort):
    output, _ = cohort
    before = (output / "cohort.json").read_bytes()
    with pytest.raises(FileExistsError):
        oracle.generate(output)
    assert (output / "cohort.json").read_bytes() == before


def test_immutable_profile_guards_and_hardware_bounds_are_still_present():
    root = Path(oracle.ROOT)
    wrapper = (
        root / "hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v"
    ).read_text()
    sync = (
        root
        / "hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v"
    ).read_text()
    tracker = (
        root / "hdl/library/axi_starlink_pss_tracker/axi_starlink_pss_tracker.v"
    ).read_text()
    assert "boundary stop requires shared 15 MS/s" in wrapper
    assert "shared-XFFT ABI 1.5 is currently restricted to 15 MS/s" in sync
    assert (
        "snapshot_health_flags & 32'h0000_57ff" in sync
    )  # Future conditioned STOP must become0x77ff, NOT changed here.
    assert "66 * RATE_MULTIPLIER" in tracker and "130 * RATE_MULTIPLIER" in tracker
    assert "60 * RATE_MULTIPLIER + 1" in tracker
    assert "fixture injection is qualified only at 15 MS/s" in tracker
    for name in ("starlink_pss_exact_reducer.v", "starlink_pss_exact_track_reducer.v"):
        reducer = (root / "hdl/library/starlink_pss_raw_correlator" / name).read_text()
        assert "-30 * RATE_MULTIPLIER" in reducer and "30 * RATE_MULTIPLIER" in reducer
        assert "!(|i_ex[47:38]) && !(|i_eh[47:31])" in reducer
