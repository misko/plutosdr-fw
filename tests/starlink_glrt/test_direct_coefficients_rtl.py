"""Direct coefficient ROM: signed payload, backpressure, cancellation and restart."""
import hashlib
import subprocess

import pytest

from tools.generate_glrt_direct_phase_rom import pack_phase_rom

from .ddc import BANK_ROOT
from .test_cubic_coefficients_rtl import BENCH


@pytest.mark.parametrize("count", [1, 17])
@pytest.mark.parametrize("reset", [False, True])
@pytest.mark.parametrize("phases", [1, 4])
def test_direct_bank_preserves_every_word_and_restarts_after_cancel(tmp_path, count, reset, phases):
    values = [[(32767-n-phase*113, -32768+n+phase*57, 71*n-13+phase*19, 29-37*n-phase*23)
               for n in range(count)] for phase in range(phases)]
    check_bank(tmp_path, values, reset)


def test_pinned_four_phase_bank_matches_every_signed_reference_coefficient(tmp_path):
    encoded = (BANK_ROOT/"native_direct_2500000_phase4_upper.mem").read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == "10c79cc95433325bdb81de5edcf186d7a952d5d5e01668e708a20d3b318996c2"
    assert pack_phase_rom(encoded, phases=4, samples=3300) == (
        BANK_ROOT/"native_direct_2500000_phase4_upper_interleaved.mem").read_bytes()
    words = [int(word,16) for word in encoded.splitlines()]
    assert len(words) == 4*3300 and all(0 <= word < 2**64 for word in words)
    signed = lambda value: value-65536 if value & 32768 else value
    rows = [tuple(signed((word >> (16*k)) & 65535) for k in range(4)) for word in words]
    check_bank(tmp_path, [rows[phase*3300:(phase+1)*3300] for phase in range(4)], False)


def check_bank(tmp_path, values, reset, *, packed=False, always_ready=False, cancel_delay=15):
    phases, count = len(values), len(values[0])
    bank = tmp_path/"bank.mem"
    phase_major = "".join(f"{sum((v & 65535) << (16*k) for k,v in enumerate(row)):016x}\n"
                           for phase in values for row in phase).encode()
    if packed:
        from tools.generate_glrt_packed_direct_rom import pack_direct_rom
        bank.write_bytes(pack_direct_rom(phase_major,phases=phases,samples=count))
    else:
        bank.write_bytes(pack_phase_rom(phase_major, phases=phases, samples=count))
    module="starlink_glrt_packed_direct_coefficients" if packed else "starlink_glrt_direct_coefficients"
    first = BENCH.index("starlink_glrt_cubic_coefficients #(")
    last = BENCH.index(" dut (", first)
    source = (BENCH[:first] + module+' #(.SAMPLE_COUNT(N),'
              '.PHASE_COUNT(PHASE_VALUE),.TEMPLATE_FILE("BANK_PATH"))' + BENCH[last:])
    source = source.replace('wire job_ready,', 'reg [2:0] job_phase=0;\nwire job_ready,')
    source = source.replace('.job_valid(job_valid),', '.job_valid(job_valid),.job_phase(job_phase),')
    source = source.replace('"%d %d %d %d\\n",resetn,flush,job_valid,output_ready',
                            '"%d %d %d %d %d\\n",resetn,flush,job_valid,output_ready,job_phase')
    source = source.replace('rc!=4', 'rc!=5')
    for key, value in {"SEGMENT_VALUE": 1, "FIRST_VALUE": 1, "COUNT_VALUE": count,
                       "BANK_PATH": bank, "PHASE_VALUE": phases}.items():
        source = source.replace(key, str(value))
    bench, trace, executable = (tmp_path/name for name in ("tb.sv", "trace", "sim"))
    bench.write_text(source)
    # Fill and stall both pipeline slots, then discard before either is consumed.
    cycles = [(1,0,1,0,phases-1)] + [(1,0,0,0,n % phases) for n in range(cancel_delay)]
    cycles += [(0,0,0,0,0) if reset else (1,1,0,0,0), (1,0,0,0,0)]
    selected = list(reversed(range(phases))) if packed else [phase % phases for phase in (3, 1, 2, 0)]
    for phase in selected:
        cycles += [(1,0,1,0,phase)]
        interval=13 if packed else 9
        cycles += [(1,0,0,int(always_ready or n % interval == 0),n % phases) for n in range(interval*count+30)]
    trace.write_text("".join(" ".join(map(str,row))+"\n" for row in cycles))
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(executable), str(bench),
                            str(BANK_ROOT/(module+".v"))],
                           capture_output=True, text=True, check=False)
    assert build.returncode == 0, build.stdout+build.stderr
    run = subprocess.run(["vvp", str(executable), f"+INPUT={trace}"],
                         capture_output=True, text=True, timeout=30, check=False)
    assert run.returncode == 0, run.stdout+run.stderr
    actual = [list(map(int,line.split()[1:])) for line in run.stdout.splitlines()
              if line.startswith("R ")]
    expected = [[n, *row, int(n==count-1), 0]
                for phase in selected for n,row in enumerate(values[phase])]
    assert actual == expected
