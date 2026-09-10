"""Frozen BEFORE any60 common-source numerical evaluation; no runtime admission."""

from copy import deepcopy

from .high_rate60_support import recipe as support_recipe

APPROVED_SUPPORT_COMMIT = "198e935813eb4eb395aba938c8bcfa953eb83309"
APPROVED_SUPPORT = {
    "tests/starlink_oracle/high_rate60_support.py": "fbd2b193f683b77a59c93d75fa2efa75856790ed7b76b20c0149436bac71ee68",
    "tests/test_starlink_high_rate60_support.py": "27009f25bce43929dbcf89b399bc5e98dbe1403787114c601caecffc6a7a8509",
}
RECIPE = {
    "cohort": "60-upper-264tap-canonical520-offline-v1",
    "source_rate_msps": 60,
    "edge": "upper",
    "support": support_recipe(),
    "preroll_canonical": 768,
    "noise_rng": "NumPy Generator(PCG64(seed)); integers(-400,401,size=(16423,2),dtype=int64); cast int16",
    "seed": 0x600052020260910,
    "source_packing": "Q16:I16",
    "coefficient_packing": "I16:Q16",
    "native_pss": "quantize_q15(projected_pss(60000000,upper)); exact replacement at native_center; no additive noise inside264 samples",
    "native_pss_half_open": [34359740384, 34359740648],
    "native_expected_winner_lag": 0,
    "identity_probes_offset_iq": {
        "0": [903, -311], "42": [-817, 209], "127": [137, 709],
        "14023": [-619, -223], "16422": [317, -911],
    },
    "request_id": 0x60000520,
    "coefficient_generation": 0x60000001,
    "visit_id": 0x60000052,
    "source_cfo_hz": 0,
    "applied_correction_hz": 0,
    "residual_cfo_hz": 0,
    "fixed_acquisition_mixers_hz": [-15_000_000, -7_500_000],
    "fixed_pilot_mixer_hz_at_canonical": -2_812_500,
    "acquisition_rounding": "two separate absolute-phase signed17 quadrant mixes/FIR_Q15/ties-even >>15/CI16 saturations; never flatten cascade",
    "fft_bits": 18,
    "fft_length": 512,
    "coarse_taps": 66,
    "stride": 447,
    "blocks": 7,
    "words_per_stage": 3584,
    "scores": 3129,
    "coarse_Eh": 1073765335,
    "kernel_memory_sha256": "7b006bac23a3c58f614728dbfdb17d28bd77defb3d6d0d24aaa76255669c0c67",
    "kernel_canonical_sha256": "497ab1527fefaf2e0c2ed0ad7260c1fc01bec6b9062a1857b66bd7ec45bedccb",
    "kernel_source": "existing conditioned_pss_x4(upper), Q15 reversed conjugate, explicitModel18 fixedFFT schedule2,0,0,0,0",
    "saturation_policy": "every stage counted; require zero fixture clips/FFT overflow/native saturation; u69 score numerator saturation explicitly counted",
    "native_tie_rule": "strict candidate_power*retained_Ex > retained_power*candidate_Ex; first qualified lag on tie",
    "source_tail_or_service_budget_frozen": False,
    "runtime_profile_or_command_admission": False,
    "scope": "offline deterministic geometry/arithmetic only; no RF accuracy, causal handoff, live deadline, actualRTL or deployment claim",
}


def recipe():
    return deepcopy(RECIPE)
