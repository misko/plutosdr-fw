"""Bit-accurate Xilinx FFT model for the 15 MS/s acquisition candidate.

This is an offline implementation model, not synthesizable RTL.  It binds the
candidate arithmetic to the FFT v9.1 C model installed with Vivado 2022.2 and
never copies the proprietary model into source control.

Contract ``starlink-xfft-bitacc-acquisition-v1``:

* 512-point radix-4 burst transforms with natural-order output;
* 24-bit fixed-point data, 16-bit phase factors, convergent rounding, and
  block-floating scaling for the sample FFT and inverse FFT;
* a fixed two-bit scale ``(2, 0, 0, 0, 0)`` for the offline template FFT;
* a one-bit safety scale in the Q1.23 complex spectrum product;
* 66 taps and 447 valid overlap-save results per block; and
* exact rational, ties-to-even conversion of the recovered correlation into
  the existing eight-bit normalized-power score.

The finite-width FFT is compared with, but is not declared identical to, the
direct integer correlator.  Qualification therefore gates both per-score error
and the final phase/cadence decision before any RTL implementation can use this
contract.
"""

from __future__ import annotations

import ctypes
import hashlib
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import numpy as np
import numpy.typing as npt

from .acquisition import (
    ACQUISITION_ORACLE_SCHEMA,
    FixedMatchScoreStream,
)

XFFT_BITACC_SCHEMA = "starlink-xfft-bitacc-acquisition-v1"
VIVADO_VERSION = "2022.2"
XFFT_VERSION = "9.1"
XFFT_ARCHITECTURE = "radix_4_burst"
XFFT_SAMPLES = 512
XFFT_VALID_OUTPUTS = 447
XFFT_DATA_BITS = 24
XFFT_FRACTION_BITS = XFFT_DATA_BITS - 1
XFFT_PHASE_FACTOR_BITS = 16
XFFT_TARGET_CLOCK_MHZ = 100
XFFT_TARGET_THROUGHPUT_MSPS = 20
TEMPLATE_SAMPLES = 66
TEMPLATE_SCALING_SCHEDULE = (2, 0, 0, 0, 0)
TEMPLATE_TOTAL_SHIFT = sum(TEMPLATE_SCALING_SCHEDULE)
SPECTRUM_PRODUCT_SHIFT = 1
SCORE_BITS = 8
PSS_KERNEL_Q23_INT32LE_SHA256 = {
    "lower": "ba7189f2648e62116a49b51028ae08671ae3856fff5dc4f6965611eeaa967f33",
    "upper": "d96c56b3d6bcd03419a57f23f3ce4929f1e478663119f5cb5ec9b14327b7ff2b",
}

INSTALLED_CMODEL_ARCHIVE = Path(
    "/opt/Xilinx/Vivado/2022.2/data/ip/xilinx/xfft_v9_1/cmodel/"
    "xfft_v9_1_bitacc_cmodel_lin64.zip"
)
INSTALLED_CMODEL_SHA256 = (
    "0f264e0e15f93fcf5df9c60e715fe51c9bcd9639b578a5ae67be4df5cf2d5f87"
)
_CMODEL_MEMBERS = (
    "libgmp.so.11",
    "libIp_xfft_v9_1_bitacc_cmodel.so",
)


class _Generics(ctypes.Structure):
    _fields_ = [
        ("C_NFFT_MAX", ctypes.c_int),
        ("C_ARCH", ctypes.c_int),
        ("C_HAS_NFFT", ctypes.c_int),
        ("C_USE_FLT_PT", ctypes.c_int),
        ("C_INPUT_WIDTH", ctypes.c_int),
        ("C_TWIDDLE_WIDTH", ctypes.c_int),
        ("C_HAS_SCALING", ctypes.c_int),
        ("C_HAS_BFP", ctypes.c_int),
        ("C_HAS_ROUNDING", ctypes.c_int),
    ]


class _Inputs(ctypes.Structure):
    _fields_ = [
        ("nfft", ctypes.c_int),
        ("xn_re", ctypes.POINTER(ctypes.c_double)),
        ("xn_re_size", ctypes.c_int),
        ("xn_im", ctypes.POINTER(ctypes.c_double)),
        ("xn_im_size", ctypes.c_int),
        ("scaling_sch", ctypes.POINTER(ctypes.c_int)),
        ("scaling_sch_size", ctypes.c_int),
        ("direction", ctypes.c_int),
    ]


class _Outputs(ctypes.Structure):
    _fields_ = [
        ("xk_re", ctypes.POINTER(ctypes.c_double)),
        ("xk_re_size", ctypes.c_int),
        ("xk_im", ctypes.POINTER(ctypes.c_double)),
        ("xk_im_size", ctypes.c_int),
        ("blk_exp", ctypes.c_int),
        ("overflow", ctypes.c_int),
    ]


@dataclass(frozen=True, slots=True)
class XfftBitAccResult:
    """Score stream plus the block-level arithmetic evidence."""

    stream: FixedMatchScoreStream
    kernel_iq: npt.NDArray[np.int32]
    kernel_sha256: str
    forward_block_exponents: tuple[int, ...]
    inverse_block_exponents: tuple[int, ...]
    forward_overflow_blocks: int
    inverse_overflow_blocks: int
    product_overflow_blocks: int
    schema: str = XFFT_BITACC_SCHEMA

    @property
    def block_count(self) -> int:
        return len(self.forward_block_exponents)


def prepare_installed_cmodel(
    output_directory: Path,
    *,
    archive: Path = INSTALLED_CMODEL_ARCHIVE,
) -> Path:
    """Validate and extract only the installed runtime libraries."""

    archive = archive.resolve(strict=True)
    observed_sha256 = _sha256_file(archive)
    if observed_sha256 != INSTALLED_CMODEL_SHA256:
        raise ValueError(
            "installed XFFT C-model archive digest does not match the frozen "
            f"Vivado 2022.2 input: {observed_sha256}"
        )
    destination = output_directory.resolve(strict=False)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
        missing = set(_CMODEL_MEMBERS) - names
        if missing:
            raise ValueError(f"XFFT C-model archive is missing {sorted(missing)}")
        for member in _CMODEL_MEMBERS:
            target = destination / member
            payload = package.read(member)
            if not target.is_file() or target.read_bytes() != payload:
                target.write_bytes(payload)
    return destination


class XfftBitAccModel:
    """Minimal ctypes owner for fixed and block-floating XFFT v9.1 states."""

    def __init__(self, cmodel_directory: Path) -> None:
        directory = cmodel_directory.resolve(strict=True)
        self._gmp = ctypes.CDLL(
            str(directory / "libgmp.so.11"), mode=ctypes.RTLD_GLOBAL
        )
        self._library = ctypes.CDLL(
            str(directory / "libIp_xfft_v9_1_bitacc_cmodel.so")
        )
        self._library.xilinx_ip_xfft_v9_1_create_state.argtypes = [_Generics]
        self._library.xilinx_ip_xfft_v9_1_create_state.restype = ctypes.c_void_p
        self._library.xilinx_ip_xfft_v9_1_destroy_state.argtypes = [ctypes.c_void_p]
        self._library.xilinx_ip_xfft_v9_1_bitacc_simulate.argtypes = [
            ctypes.c_void_p,
            _Inputs,
            ctypes.POINTER(_Outputs),
        ]
        self._library.xilinx_ip_xfft_v9_1_bitacc_simulate.restype = ctypes.c_int
        self._fixed_state = self._create_state(block_floating=False)
        self._block_floating_state = self._create_state(block_floating=True)
        self._closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_unused: object) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._library.xilinx_ip_xfft_v9_1_destroy_state(self._fixed_state)
            self._library.xilinx_ip_xfft_v9_1_destroy_state(
                self._block_floating_state
            )
            self._closed = True

    def fixed_transform(
        self,
        values: npt.ArrayLike,
        *,
        direction: int,
        schedule: tuple[int, int, int, int, int],
    ) -> tuple[npt.NDArray[np.complex128], int, bool]:
        return self._simulate(
            self._fixed_state, values, direction=direction, schedule=schedule
        )

    def block_floating_transform(
        self,
        values: npt.ArrayLike,
        *,
        direction: int,
    ) -> tuple[npt.NDArray[np.complex128], int, bool]:
        return self._simulate(
            self._block_floating_state,
            values,
            direction=direction,
            schedule=(0, 0, 0, 0, 0),
        )

    def _create_state(self, *, block_floating: bool) -> ctypes.c_void_p:
        # C_ARCH=1 is radix-4 burst.  The remaining flags mirror the generated
        # 24-bit candidate core, including convergent rounding.
        state = self._library.xilinx_ip_xfft_v9_1_create_state(
            _Generics(
                9,
                1,
                0,
                0,
                XFFT_DATA_BITS,
                XFFT_PHASE_FACTOR_BITS,
                1,
                int(block_floating),
                1,
            )
        )
        if not state:
            raise RuntimeError("XFFT C model refused the frozen generic set")
        return state

    def _simulate(
        self,
        state: ctypes.c_void_p,
        values: npt.ArrayLike,
        *,
        direction: int,
        schedule: tuple[int, int, int, int, int],
    ) -> tuple[npt.NDArray[np.complex128], int, bool]:
        if self._closed:
            raise RuntimeError("XFFT C model is closed")
        if direction not in (0, 1):
            raise ValueError("XFFT direction must be inverse 0 or forward 1")
        samples = np.asarray(values, dtype=np.complex128)
        if samples.shape != (XFFT_SAMPLES,) or not np.all(np.isfinite(samples)):
            raise ValueError("XFFT input must contain 512 finite complex samples")
        real = np.ascontiguousarray(samples.real, dtype=np.float64)
        imag = np.ascontiguousarray(samples.imag, dtype=np.float64)
        output_real = np.empty(XFFT_SAMPLES, dtype=np.float64)
        output_imag = np.empty(XFFT_SAMPLES, dtype=np.float64)
        scaling = (ctypes.c_int * len(schedule))(*schedule)
        inputs = _Inputs(
            9,
            real.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            XFFT_SAMPLES,
            imag.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            XFFT_SAMPLES,
            scaling,
            len(schedule),
            direction,
        )
        outputs = _Outputs(
            output_real.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            XFFT_SAMPLES,
            output_imag.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            XFFT_SAMPLES,
            0,
            0,
        )
        status = self._library.xilinx_ip_xfft_v9_1_bitacc_simulate(
            state, inputs, ctypes.byref(outputs)
        )
        if status != 0:
            raise RuntimeError(f"XFFT C-model simulation failed with status {status}")
        if (
            outputs.xk_re_size != XFFT_SAMPLES
            or outputs.xk_im_size != XFFT_SAMPLES
        ):
            raise RuntimeError("XFFT C model returned an unexpected output size")
        transformed = np.asarray(output_real + 1j * output_imag, np.complex128)
        transformed.flags.writeable = False
        return transformed, int(outputs.blk_exp), bool(outputs.overflow)


def xfft_bitacc_match_scores(
    samples_iq: npt.ArrayLike,
    coefficients_iq: npt.ArrayLike,
    model: XfftBitAccModel,
    *,
    first_sample_index: int = 0,
) -> XfftBitAccResult:
    """Run the complete finite-width overlap-save scoring candidate."""

    samples = _ci16_matrix(samples_iq, "samples_iq")
    coefficients = _ci16_matrix(coefficients_iq, "coefficients_iq")
    if coefficients.shape != (TEMPLATE_SAMPLES, 2):
        raise ValueError("XFFT acquisition requires exactly 66 coefficient taps")
    if samples.shape[0] < TEMPLATE_SAMPLES:
        raise ValueError("samples must contain at least one complete template")
    if (
        isinstance(first_sample_index, bool)
        or not isinstance(first_sample_index, int)
        or first_sample_index < 0
        or first_sample_index > (1 << 63) - 1
    ):
        raise ValueError("first_sample_index must fit nonnegative signed 64 bits")

    kernel_iq = _template_kernel(coefficients, model)
    kernel_complex = _fixed_to_complex(kernel_iq, XFFT_DATA_BITS)
    kernel_sha256 = hashlib.sha256(
        np.asarray(kernel_iq, dtype="<i4").tobytes(order="C")
    ).hexdigest()

    sample_power = (
        samples[:, 0] * samples[:, 0] + samples[:, 1] * samples[:, 1]
    )
    cumulative_energy = np.empty(samples.shape[0] + 1, dtype=np.int64)
    cumulative_energy[0] = 0
    np.cumsum(sample_power, dtype=np.int64, out=cumulative_energy[1:])
    window_energy = (
        cumulative_energy[TEMPLATE_SAMPLES:]
        - cumulative_energy[:-TEMPLATE_SAMPLES]
    )
    coefficient_energy = int(
        np.sum(
            coefficients[:, 0] * coefficients[:, 0]
            + coefficients[:, 1] * coefficients[:, 1],
            dtype=np.int64,
        )
    )

    output_count = samples.shape[0] - TEMPLATE_SAMPLES + 1
    scores = np.empty(output_count, dtype=np.uint32)
    forward_exponents: list[int] = []
    inverse_exponents: list[int] = []
    forward_overflows = inverse_overflows = product_overflows = 0
    padded = np.zeros(XFFT_SAMPLES, dtype=np.complex128)
    for output_start in range(0, output_count, XFFT_VALID_OUTPUTS):
        count = min(XFFT_VALID_OUTPUTS, output_count - output_start)
        padded.fill(0)
        source = samples[output_start : output_start + XFFT_SAMPLES]
        padded[: source.shape[0]] = (
            source[:, 0] + 1j * source[:, 1]
        ) / float(1 << 15)
        forward, forward_exponent, forward_overflow = (
            model.block_floating_transform(padded, direction=1)
        )
        forward_exponents.append(forward_exponent)
        forward_overflows += int(forward_overflow)

        try:
            product = _multiply_spectrum(forward, kernel_complex)
        except OverflowError:
            product_overflows += 1
            raise
        inverse, inverse_exponent, inverse_overflow = (
            model.block_floating_transform(product, direction=0)
        )
        inverse_exponents.append(inverse_exponent)
        inverse_overflows += int(inverse_overflow)
        correlation_iq = _complex_to_fixed(
            inverse[TEMPLATE_SAMPLES - 1 : TEMPLATE_SAMPLES - 1 + count],
            XFFT_DATA_BITS,
        )

        # IFFT is unnormalized.  Recovering the CI16/Q1.15 dot product from a
        # Q1.23 output leaves this exact power-of-two scale:
        # 2**(21 + Ef + template_shift + product_shift + Ei - 23).
        correlation_shift = (
            21
            + forward_exponent
            + TEMPLATE_TOTAL_SHIFT
            + SPECTRUM_PRODUCT_SHIFT
            + inverse_exponent
            - XFFT_FRACTION_BITS
        )
        if correlation_shift < 0:
            raise ArithmeticError("unexpected negative correlation scale")
        scores[output_start : output_start + count] = _normalized_scores(
            correlation_iq,
            window_energy[output_start : output_start + count],
            coefficient_energy,
            correlation_shift,
        )

    if forward_overflows or inverse_overflows or product_overflows:
        raise ArithmeticError("finite-width acquisition overflowed")
    scores.flags.writeable = False
    kernel_iq.flags.writeable = False
    stream = FixedMatchScoreStream(
        first_sample_index=first_sample_index,
        scores=scores,
        template_samples=TEMPLATE_SAMPLES,
        coefficient_energy=coefficient_energy,
        fft_samples=XFFT_SAMPLES,
        maximum_fft_rounding_residual=math.nan,
        schema=ACQUISITION_ORACLE_SCHEMA,
    )
    return XfftBitAccResult(
        stream=stream,
        kernel_iq=kernel_iq,
        kernel_sha256=kernel_sha256,
        forward_block_exponents=tuple(forward_exponents),
        inverse_block_exponents=tuple(inverse_exponents),
        forward_overflow_blocks=forward_overflows,
        inverse_overflow_blocks=inverse_overflows,
        product_overflow_blocks=product_overflows,
    )


def _template_kernel(
    coefficients: npt.NDArray[np.int64], model: XfftBitAccModel
) -> npt.NDArray[np.int32]:
    padded = np.zeros(XFFT_SAMPLES, dtype=np.complex128)
    coefficient_complex = coefficients[:, 0] + 1j * coefficients[:, 1]
    padded[:TEMPLATE_SAMPLES] = np.conj(coefficient_complex[::-1]) / float(
        1 << 15
    )
    transformed, _unused_exponent, overflow = model.fixed_transform(
        padded, direction=1, schedule=TEMPLATE_SCALING_SCHEDULE
    )
    if overflow:
        raise ArithmeticError("fixed template FFT overflowed")
    return _complex_to_fixed(transformed, XFFT_DATA_BITS)


def _multiply_spectrum(
    left: npt.NDArray[np.complex128],
    right: npt.NDArray[np.complex128],
) -> npt.NDArray[np.complex128]:
    left_iq = _complex_to_fixed(left, XFFT_DATA_BITS).astype(np.int64)
    right_iq = _complex_to_fixed(right, XFFT_DATA_BITS).astype(np.int64)
    real = left_iq[:, 0] * right_iq[:, 0] - left_iq[:, 1] * right_iq[:, 1]
    imag = left_iq[:, 0] * right_iq[:, 1] + left_iq[:, 1] * right_iq[:, 0]
    product_iq = np.column_stack(
        (
            _round_shift_ties_even(
                real, XFFT_FRACTION_BITS + SPECTRUM_PRODUCT_SHIFT
            ),
            _round_shift_ties_even(
                imag, XFFT_FRACTION_BITS + SPECTRUM_PRODUCT_SHIFT
            ),
        )
    )
    minimum = -(1 << XFFT_FRACTION_BITS)
    maximum = (1 << XFFT_FRACTION_BITS) - 1
    if np.any(product_iq < minimum) or np.any(product_iq > maximum):
        raise OverflowError("Q1.23 complex spectrum product overflowed")
    return _fixed_to_complex(product_iq, XFFT_DATA_BITS)


def _normalized_scores(
    correlation_iq: npt.NDArray[np.int32],
    sample_energy: npt.NDArray[np.int64],
    coefficient_energy: int,
    correlation_shift: int,
) -> npt.NDArray[np.uint32]:
    full_scale = (1 << SCORE_BITS) - 1
    scale_squared = 1 << (2 * correlation_shift)
    scores = np.empty(correlation_iq.shape[0], dtype=np.uint32)
    for index, (correlation, energy) in enumerate(
        zip(correlation_iq, sample_energy, strict=True)
    ):
        real = int(correlation[0])
        imag = int(correlation[1])
        numerator = (real * real + imag * imag) * scale_squared
        denominator = int(energy) * coefficient_energy
        scores[index] = _round_normalized_power(
            numerator, denominator, full_scale=full_scale
        )
    return scores


def _round_normalized_power(
    numerator: int, denominator: int, *, full_scale: int
) -> int:
    if numerator <= 0 or denominator <= 0:
        return 0
    if numerator >= denominator:
        return full_scale
    quotient, remainder = divmod(numerator * full_scale, denominator)
    doubled = 2 * remainder
    if doubled > denominator or (doubled == denominator and quotient & 1):
        quotient += 1
    return quotient


def _round_shift_ties_even(
    values: npt.NDArray[np.int64], shift: int
) -> npt.NDArray[np.int64]:
    if shift <= 0:
        raise ValueError("rounding shift must be positive")
    divisor = 1 << shift
    quotient = values // divisor
    remainder = values - quotient * divisor
    doubled = remainder * 2
    increment = (doubled > divisor) | ((doubled == divisor) & ((quotient & 1) != 0))
    return quotient + increment.astype(np.int64)


def _complex_to_fixed(
    values: npt.ArrayLike, width: int
) -> npt.NDArray[np.int32]:
    samples = np.asarray(values, dtype=np.complex128)
    if samples.ndim != 1 or not np.all(np.isfinite(samples)):
        raise ValueError("fixed-point conversion requires finite complex samples")
    fraction_bits = width - 1
    scale = 1 << fraction_bits
    converted = np.column_stack(
        (np.rint(samples.real * scale), np.rint(samples.imag * scale))
    ).astype(np.int64)
    minimum = -scale
    maximum = scale - 1
    if np.any(converted < minimum) or np.any(converted > maximum):
        raise OverflowError(f"complex value does not fit signed Q1.{fraction_bits}")
    return np.asarray(converted, dtype=np.int32)


def _fixed_to_complex(values: npt.ArrayLike, width: int) -> npt.NDArray[np.complex128]:
    samples = np.asarray(values, dtype=np.int64)
    if samples.ndim != 2 or samples.shape[1:] != (2,):
        raise ValueError("fixed complex values must have shape (N, 2)")
    scale = float(1 << (width - 1))
    return np.asarray((samples[:, 0] + 1j * samples[:, 1]) / scale, np.complex128)


def _ci16_matrix(values: npt.ArrayLike, name: str) -> npt.NDArray[np.int64]:
    raw = np.asarray(values)
    if (
        raw.ndim != 2
        or raw.shape[1:] != (2,)
        or not np.issubdtype(raw.dtype, np.integer)
    ):
        raise ValueError(f"{name} must be an integer matrix with shape (N, 2)")
    converted = np.asarray(raw, dtype=np.int64)
    if np.any(converted < -(1 << 15)) or np.any(converted > (1 << 15) - 1):
        raise ValueError(f"{name} components must fit signed 16 bits")
    return converted


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
