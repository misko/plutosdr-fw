"""Serial rotation faults close exact delivered prefixes and allow fresh jobs."""
import pytest

from .test_native_engine_rtl import bank_for, expected, row, sample, simulate


def direct_coefficients(count):
    direct = [(n*13-700, n*17+900, n*5-300, n*7+400) for n in range(count)]
    return direct, [[n, *c, int(n == count-1), 0] for n, c in enumerate(direct)]


def spaced_job(job, count):
    rows = [row(job=job)] + [row()]*59
    for n in range(count):
        rows += [row(value=sample(job[0]+n), closed=int(n == count-1))] + [row()]*39
    return rows


@pytest.mark.parametrize("count", [32, 96])
@pytest.mark.parametrize("offset", range(1, 18))
def test_collision_including_last_input_closes_delivered_prefix_and_recovers(tmp_path, count, offset):
    direct, coefficients = direct_coefficients(count)
    first, second = (1000, 2**32-3, 1777), (5000, 17, 2**32-7331)
    prefix_count = count-2 if count == 32 else 1
    rows = [row(job=first)] + [row()]*59
    for n in range(prefix_count):
        rows += [row(value=sample(first[0]+n))] + [row()]*39
    rows += [row(value=sample(first[0]+prefix_count))] + [row()]*(offset-1)
    rows += [row(value=sample(first[0]+prefix_count+1), closed=int(count == 32))]
    rows += [row()]*50 + spaced_job(second, count)
    assert simulate(tmp_path, count, bank_for(count*24), rows, 24, direct, serial=True) == [
        expected(first, [sample(first[0]+n) for n in range(prefix_count)], coefficients, 2),
        expected(second, [sample(second[0]+n) for n in range(count)], coefficients),
    ]


@pytest.mark.parametrize("failure,fault", [("gap", 1), ("closed", 2), ("flush", 8), ("reset", None)])
@pytest.mark.parametrize("offset", range(1, 24))
def test_cancellation_at_each_stage_preserves_only_delivered_products(tmp_path, failure, fault, offset):
    count = 96
    direct, coefficients = direct_coefficients(count)
    first, second = (1000, 99, 7131), (5000, 821, 2**32-31)
    rows = [row(job=first)] + [row()]*59
    rows += [row(value=sample(first[0]))] + [row()]*39
    rows += [row(value=sample(first[0]+1))] + [row()]*(offset-1)
    rows += [row(**{failure: 0 if failure == "reset" else 1})]
    rows += [row()]*50 + spaced_job(second, count)
    truth = [] if fault is None else [
        expected(first, [sample(first[0]+n) for n in range(1+int(offset > 22))], coefficients, fault)]
    truth.append(expected(second, [sample(second[0]+n) for n in range(count)], coefficients))
    assert simulate(tmp_path, count, bank_for(count*24), rows, 24, direct, serial=True) == truth
