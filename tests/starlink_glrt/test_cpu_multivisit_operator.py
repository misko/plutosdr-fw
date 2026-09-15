"""Pure admission and result checks for bounded multi-frequency qualification."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest


@pytest.fixture(scope='module')
def operator():
    name='qualify_glrt_cpu_live20'
    prior=sys.modules.get(name)
    sys.modules[name]=ModuleType(name)
    try:
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('multivisit_operator',
            root/'scripts/qualify_glrt_cpu_multivisit20.py')
        result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
        yield result
    finally:
        if prior is None: sys.modules.pop(name,None)
        else: sys.modules[name]=prior


def wire(**changes):
    value={'scope':'bounded_live_cpu_acquisition_native_feedback','rate':30000000,
           'status':0,'blocks':45000,'attempts':256,'handoffs':0,
           'native_results':0,'native_completed_runs':0,'worker_complete':1}
    value.update(changes)
    return (json.dumps(value)+'\n').encode()


def test_plan_is_distinct_reviewed_upper_edges_and_under_thirty_minutes(operator):
    assert operator.validate_los([1940312500,1190312500,1440312500,1690312500]) == \
        (1940312500,1190312500,1440312500,1690312500)
    assert 4*operator.SOURCE_SECONDS_PER_VISIT < 20*60 < 30*60
    for values in ([],[1690312500]*2,[1709687500],list(operator.UPPER_EDGE_LOS)+[1190312500]):
        with pytest.raises(ValueError): operator.validate_los(values)


def test_only_consistent_completed_track_stops_the_plan(operator):
    status,complete=operator.decode_status(wire(),30000000)
    assert not complete and status['attempts']==256
    status,complete=operator.decode_status(wire(native_completed_runs=1,native_results=7500,
                                                 handoffs=1,attempts=17),30000000)
    assert complete and status['native_results']==7500
    for raw in (wire(native_completed_runs=1,native_results=7499,handoffs=1),
                wire(native_completed_runs=1,native_results=7500,handoffs=0),
                wire(status=1),wire(rate=60000000),wire()+b'{}\n'):
        with pytest.raises(ValueError): operator.decode_status(raw,30000000)
