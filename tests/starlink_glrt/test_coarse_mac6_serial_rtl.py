"""Two-clock coarse MAC: exact CI16/CI12 sums, collision and flush fencing."""
from pathlib import Path
import random
import subprocess

import pytest

from .test_coarse_mac6_rtl import BENCH


def simulate(tmp_path, rows):
    stimulus=tmp_path/'input.txt'
    stimulus.write_text('\n'.join(rows)+'\n')
    bench=tmp_path/'tb.sv'
    bench.write_text(BENCH.replace('starlink_glrt_coarse_mac6 dut',
                                  'starlink_glrt_coarse_mac6_serial dut'))
    rtl=Path(__file__).parents[2]/'hdl/library/starlink_glrt/starlink_glrt_coarse_mac6.v'
    executable=tmp_path/'sim'
    subprocess.run(['iverilog','-g2012','-s','tb','-o',str(executable),str(bench),str(rtl)],
                   check=True,capture_output=True,text=True)
    result=subprocess.run(['vvp',str(executable),f'+INPUT={stimulus}'],check=True,
                          capture_output=True,text=True,timeout=20)
    (tmp_path/'simulation.log').write_text(result.stdout+result.stderr)
    return [tuple(int(v,16) for v in line.split()[1:]) for line in result.stdout.splitlines()
            if line.startswith('R ')], result.stdout


IDLE='1 0 0 0 0 123 -321 abcdef 98765432'
RESET='0 0 0 0 0 0 0 0 0'
FLUSH='1 1 0 0 0 0 0 0 0'


def job(rng, tag, extra_bubbles=False):
    rows=[];re=[0]*6;im=[0]*6;energy=0
    for tap in range(11):
        i,q=(-32768,-32768) if tag==0 else (rng.randrange(-32768,32768),rng.randrange(-32768,32768))
        coeff=[(-2048,2047) if tag==0 else (rng.randrange(-2048,2048),rng.randrange(-2048,2048))
               for _ in range(6)]
        packed=sum(((a&4095)|((b&4095)<<12))<<(lane*24) for lane,(a,b) in enumerate(coeff))
        rows += [f'1 0 1 {int(tap==0)} {int(tap==10)} {i} {q} {packed:x} {tag:x}',IDLE]
        if extra_bubbles and tap%3==1:
            rows += [IDLE]*2
        energy += i*i+q*q
        for lane,(a,b) in enumerate(coeff):
            re[lane] += i*a+q*b;im[lane] += q*a-i*b
    return rows,(tag,sum((x&0xffffffff)<<(lane*32) for lane,x in enumerate(re)),
                sum((x&0xffffffff)<<(lane*32) for lane,x in enumerate(im)),energy)


def test_exact_extrema_random_and_adjacent_jobs_with_changing_idle_inputs(tmp_path):
    rng=random.Random(2116000750)
    rows=[RESET]*2;expected=[]
    for tag in range(100):
        generated,truth=job(rng,tag,tag%2==0)
        rows += generated;expected.append(truth)
    actual,log=simulate(tmp_path,rows+[IDLE]*4)
    assert actual==expected and '\nF\n' not in log


@pytest.mark.parametrize('interruption',['collision','early_last','tag','flush','reset'])
@pytest.mark.parametrize('position',[1,2,10,20,21])
def test_interruption_fences_partial_jobs_and_recovers(tmp_path,interruption,position):
    rng=random.Random(771)
    generated,_=job(rng,11)
    # Positions include both operand phases and the last tap's pending Q.
    if interruption=='collision':
        position |= 1
        damage='1 0 1 0 0 1 2 1 b'
    elif interruption=='early_last':
        position=position//2*2
        damage='1 0 1 0 1 1 2 1 b' if position<20 else '1 0 1 0 0 1 2 1 b'
    elif interruption=='tag':
        position=max(2,position//2*2)
        damage='1 0 1 0 0 1 2 1 c'
    else:
        damage=FLUSH if interruption=='flush' else RESET
    rows=[RESET]*2+generated[:position]+[damage]+[IDLE]*4
    recovery,truth=job(rng,999)
    rows += [FLUSH]+recovery+[IDLE]*4
    actual,log=simulate(tmp_path,rows)
    assert actual==[truth]
    if interruption in ('collision','early_last','tag'):
        assert '\nF\n' in log
    else:
        assert '\nF\n' not in log
