"""Four-clock pairs through folded roots/division, checked with integer math."""
import random

from .test_verify_norm_rtl import expected, simulate


def test_four_clock_pairs_preserve_exact_roots_scores_tags_and_latency(tmp_path):
    rng = random.Random(240603333)
    limits = [0,1,2,3,4,8,9,15,16,2**32-1,2**32,2**63-1,2**64-1]
    cases = [(n,d) for n in limits for d in limits]
    cases += [(rng.randrange(2**64),rng.randrange(2**64)) for _ in range(2000)]
    rows,wanted = ["0 0 0 0 0 0"],[]
    for tag,(n,d) in enumerate(cases):
        cycle = len(rows)
        rows += [f"1 0 1 {n:x} {d:x} {tag:x}"]+["1 0 0 0 0 0"]*3
        wanted.append((cycle+49,*expected(tag,n,d)))
        if tag%6 == 5:
            rows += ["1 0 0 0 0 0"]*rng.randrange(1,5)
    rows += ["1 0 0 0 0 0"]*56
    actual,faults = simulate(tmp_path,rows,folded_root=True)
    assert not faults
    assert actual == wanted


def test_reset_flush_at_every_folded_phase_discards_unfinished_pairs(tmp_path):
    rows,wanted = ["0 0 0 0 0 0"],[]
    tag = 0
    for reset in (False,True):
        for offset in range(56):
            pending = []
            for i in range(offset):
                tag += 1
                n,d = tag*tag,(tag+11)**2
                valid = i%4 == 0
                cycle = len(rows)
                rows.append(f"1 0 {int(valid)} {n:x} {d:x} {tag:x}")
                if valid:
                    pending.append((cycle+49,*expected(tag,n,d)))
            wanted += [r for r in pending if r[0] < len(rows)]
            rows.append("0 0 1 ffff 1 ffffffff" if reset else "1 1 1 ffff 1 ffffffff")
            rows += ["1 0 0 0 0 0"]*56
            tag += 1
            wanted.append((len(rows)+49,*expected(tag,4,9)))
            rows += [f"1 0 1 4 9 {tag:x}"]+["1 0 0 0 0 0"]*56
    actual,faults = simulate(tmp_path,rows,folded_root=True)
    assert not faults
    assert actual == wanted


def test_input_in_any_reserved_phase_faults_closed_until_flush(tmp_path):
    rows,wanted,wanted_faults = ["0 0 0 0 0 0"],[],[]
    tag = 0
    for offset in range(1,80):
        if offset%4 == 0:
            continue
        pending = []
        for i in range(offset):
            tag += 1
            cycle = len(rows)
            rows.append(f"1 0 {int(i%4 == 0)} 4 9 {tag:x}")
            if i%4 == 0:
                pending.append((cycle+49,*expected(tag,4,9)))
        fault_cycle = len(rows)
        wanted += [r for r in pending if r[0] < fault_cycle]
        rows += ["1 0 1 9 10 ffffffff"]+["1 0 0 0 0 0"]*56
        wanted_faults += list(range(fault_cycle,len(rows)))
        rows += ["1 1 0 0 0 0"]+["1 0 0 0 0 0"]*56
    actual,faults = simulate(tmp_path,rows,folded_root=True)
    assert actual == wanted
    assert faults == wanted_faults
