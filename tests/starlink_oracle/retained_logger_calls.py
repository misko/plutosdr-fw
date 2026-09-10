"""Exact two-site logging-only inverse; no task, format, numeric or clock change."""
import hashlib

ORIGINAL_SHA = "3e0c8258c3bdb3a6005186ff17ec15547822e6d69e620b154bbc8582ea968d6a"
ORIGINAL_BENCH_SHA = "713dac6ec03abea20a8899692f5312de89a2988df0dc1ef5e300d5ea30b2fb89"
ORIGINAL_CSV_SHA = "07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa"
SITES = (
    ('input', 'actual_inputs', '`D.core_input_data', '0'),
    ('raw', 'actual_raw', '`D.core_output_data', "{5'b0,actual_exponent}"),
)


def replacements():
    result = []
    for family, position, data, exponent in SITES:
        args = f'actual_fixture,{position},{data},actual_start,{exponent}'
        old = f'      actual_word(actual_inverse?"{family}I":"{family}F",{args});\n'
        new = (f'      if(actual_inverse)actual_word("{family}I",{args});\n'
               f'      else actual_word("{family}F",{args});\n')
        result.append((old, new))
    return result


def inverse(text, *, bench=False):
    for old, new in replacements():
        if text.count(new) != 1 or old in text:
            raise ValueError('logger two-site inverse boundaries')
        text = text.replace(new, old, 1)
    expected = ORIGINAL_BENCH_SHA if bench else ORIGINAL_SHA
    if hashlib.sha256(text.encode()).hexdigest() != expected:
        raise ValueError('logger complete-source inverse')
    return text
