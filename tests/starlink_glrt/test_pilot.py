from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from .ddc import BANK_ROOT, RATES
from .pilot import acquisition_fixed, acquisition_surface, frame, score, symbol_samples, templates


def test_native_rom_freeze_matches_numerical_spec():
    manifest = json.loads((BANK_ROOT / "native_templates.json").read_text())
    for name, spec in manifest["files"].items():
        raw = (BANK_ROOT / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
        assert len(raw.split()) == spec["words"]
    for rate in RATES:
        for edge in ("upper", "lower"):
            words = np.array([int(v, 16) for v in (BANK_ROOT / f"pilot_{rate}_{edge}_q7.mem").read_text().split()])
            unpacked = np.column_stack((words & 255, words >> 8)).astype(np.uint8).view(np.int8)
            expected = templates(rate, edge)[np.arange(-17, 64) % 300].reshape(-1, 2)
            assert np.array_equal(unpacked, expected)


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("edge", ["upper", "lower"])
def test_strong_pilot_glrt_and_rolled_control(rate, edge):
    n = symbol_samples(rate)
    pilot = frame(rate, edge)
    index = np.arange(len(pilot))
    signal = 5000*pilot*np.exp(2j*np.pi*42000*index/rate)
    rng = np.random.default_rng(7721)
    signal += 1500*(rng.normal(size=len(pilot)) + 1j*rng.normal(size=len(pilot)))
    raw = np.rint(np.column_stack((signal.real, signal.imag))).astype(np.int16)
    result = score(raw, rate, edge, 0)
    assert result.exact > .85 and result.margin > .65
    assert abs(result.cfo_hz - 42000) < 500
    assert n == rate*22//5_000_000
    wrong = frame(rate, edge, roll=17)*5000
    raw = np.rint(np.column_stack((wrong.real, wrong.imag))).astype(np.int16)
    control = score(raw, rate, edge, 0)
    assert control.control > .98 and control.margin < -.7


@pytest.mark.parametrize("edge", ["upper", "lower"])
def test_blind_proposal_recovers_unseeded_epoch(edge):
    rng = np.random.default_rng(71819)
    noise = 1000*(rng.normal(size=11000) + 1j*rng.normal(size=11000))
    epoch = 751
    pilot = frame(2_500_000, edge)
    noise[epoch:epoch+len(pilot)] += 5000*pilot
    surface = acquisition_surface(noise, edge)
    assert int(np.argmax(surface)) == epoch
    assert surface[epoch] > .8


@pytest.mark.parametrize("edge",["upper","lower"])
def test_fixed_acquisition_energy_model_and_roll_ambiguity(edge):
    rng=np.random.default_rng(14903)
    base=2000*(rng.normal(size=5000)+1j*rng.normal(size=5000))
    epoch=331
    for roll in (0,17):
        values=base.copy()
        pilot=frame(2500000,edge,roll=roll)
        values[epoch:epoch+len(pilot)]+=5000*pilot
        iq=np.rint(np.column_stack((values.real,values.imag))).astype(np.int16)
        numerator,energy=acquisition_fixed(iq,edge)
        fixed=numerator/(44*np.maximum(energy,1))
        floating=acquisition_surface(iq[:,0].astype(float)+1j*iq[:,1],edge)
        bank=templates(2500000,edge)[:16].astype(float)
        coefficient_energy=np.sum(bank**2,axis=(1,2))/(11*32**2)
        relative_bound=float(max(abs(coefficient_energy-1)))
        assert np.all(abs(fixed[22:]-floating) <= relative_bound*floating+2e-5)
        # This is a known sequence at a shifted timing, NOT a blind negative.
        assert int(np.argmax(fixed))-22==epoch+roll*11
