"""Independent startup-carrier review over retained worker records.

Call after checking the IQ, numerical estimates and support decisions. This
checks causal prediction, not signal detection, source continuity or accuracy.
"""
import math

import numpy as np


def review_startup_carrier(resolved_hz, past):
    assert math.isfinite(resolved_hz) and abs(resolved_hz)+250<1250000
    previous=[];last=resolved_hz;forecasts=0
    for index,row in enumerate(past[:8]):
        assert row['frame']==index*9 and row['accepted'] in (0,1)
        assert 0<=row['phase_step']<2**32 and math.isfinite(row['cfo_hz'])
        predicted=last
        if index>=3 and len(previous)==index:
            frames=np.array([p['frame'] for p in previous],dtype=float)
            values=np.array([p['cfo_hz'] for p in previous])
            slope,center=np.linalg.lstsq(
                np.column_stack((frames-frames.mean(),np.ones(len(frames)))),values,rcond=None)[0]
            proposed=center+slope*(row['frame']-frames.mean())
            if np.isfinite(proposed) and abs(proposed)+250<1250000 and abs(proposed-last)<=250:
                predicted=proposed;forecasts+=1
        step=row['phase_step'];hz=(step if step<2**31 else step-2**32)*2500000/2**32
        # Independent least squares and Q32 carrier rounding agree within one
        # phase-step LSB. This frame's estimate enters only the next prediction.
        assert abs(hz-predicted)<=2500000/2**32+1e-7
        if row['accepted']:
            previous.append(row);last=row['cfo_hz']
    return dict(initial_jobs_checked=min(8,len(past)),causal_forecasts_checked=forecasts)
