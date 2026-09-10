"""Declaration-only proof; Icarus cannot establish the XSim diagnostic is fixed."""
import hashlib
from pathlib import Path
import subprocess

import pytest

from tests.starlink_oracle import retained_completion_declaration as d
from tests.starlink_oracle import retained_output_actual as a

ROOT = Path(__file__).resolve().parents[1]


def test_exact_whole_source_inverse_and_declaration_before_uses():
    text = (ROOT / d.PATH).read_text()
    restored = d.inverse(text)
    assert hashlib.sha256(restored.encode()).hexdigest() == d.ORIGINAL_SHA
    assert text.index(d.DECLARATION) < text.index('.transfer_consumed(completion_accept')
    assert text.index(d.DECLARATION) < text.index('.producer_closed(completion_accept)')
    assert text.count(d.DECLARATION) == text.count(d.NEW) == 1


@pytest.mark.parametrize('kind', ['missing_decl', 'late_decl', 'duplicate_decl', 'missing_assign',
                                  'changed_rhs', 'changed_reset', 'changed_guard', 'unrelated_edit'])
def test_two_edit_inverse_rejects_mutants(kind):
    text = (ROOT / d.PATH).read_text()
    if kind == 'missing_decl':
        text = text.replace(d.DECLARATION, '')
    elif kind == 'late_decl':
        text = text.replace(d.DECLARATION, '').replace(d.NEW, d.DECLARATION + d.NEW)
    elif kind == 'duplicate_decl':
        text = text.replace(d.DECLARATION, d.DECLARATION * 2)
    elif kind == 'missing_assign':
        text = text.replace(d.NEW, d.OLD)
    elif kind == 'changed_rhs':
        text = text.replace('!core_status_valid && !core_output_valid;', '!core_status_valid || !core_output_valid;')
    elif kind == 'changed_reset':
        text = text.replace('completion_receipt <= 0;', 'completion_receipt <= 1;')
    elif kind == 'changed_guard':
        text = text.replace('.producer_closed(completion_accept)', ".producer_closed(1'b0)")
    else:
        text += '\n'
    with pytest.raises(ValueError, match='inverse'):
        d.inverse(text)


def test_exact_expression_known_and_four_state_control_equivalence(tmp_path):
    """Use the pinned full RHS, not a rewritten mathematical model."""
    text = (ROOT / d.PATH).read_text()
    original = d.inverse(text)
    old_statement = original[original.index(d.OLD):original.index(';', original.index(d.OLD)) + 1]
    new_statement = text[text.index(d.NEW):text.index(';', text.index(d.NEW)) + 1]
    assert old_statement.removeprefix('  wire ') == new_statement.removeprefix('  assign ')
    signals = ('completion_receipt,next_inverse,producer_transfer_receipt,guard_busy[0],'
               'forward_handoff_ack,any_fast_fault,certified_input_beat,certified_input_complete,'
               'event_frame,core_status_valid,core_output_valid')
    bench = '''`timescale 1ns/1ps
module tb;
  localparam ACK_DRAIN=7;
  reg[3:0] state;
  reg completion_receipt,next_inverse,producer_transfer_receipt;
  reg[1:0] guard_busy;
  reg forward_handoff_ack,any_fast_fault,certified_input_beat,certified_input_complete;
  reg event_frame,core_status_valid,core_output_valid;
  wire completion_accept;
''' + new_statement + '\n' + old_statement.replace('completion_accept =', 'old_accept =') + '''
  integer i,j,checks=0;
  reg[10:0] controls;
  task check;
    begin
      #1;
      if(completion_accept!==old_accept)$fatal(1,"expression mismatch");
      if(state!=ACK_DRAIN && completion_accept!==0)$fatal(1,"unowned completion must be known zero");
      checks=checks+1;
    end
  endtask
  initial begin
    guard_busy=0;
    for(i=0;i<32768;i=i+1)begin
      state=i[3:0];{''' + signals + '''}=i[14:4];check();
    end
    for(i=0;i<16;i=i+1)begin
      state=i;
      for(j=0;j<11;j=j+1)begin
        controls=11'b00001000000;controls[j]=1'bx;
        {''' + signals + '''}=controls;check();
        controls[j]=1'bz;{''' + signals + '''}=controls;check();
      end
    end
    if(checks!=33120)$fatal(1,"inventory");
    $display("OFFLINE_DECLARATION_EXPRESSION_PASS checks=%0d NOT_XSIM_REPRODUCTION",checks);
    $finish;
  end
endmodule
'''
    path = tmp_path / 'expression.sv'
    path.write_text(bench)
    compile_result = subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(tmp_path / 'sim.vvp'), str(path)],
                                    capture_output=True, text=True, timeout=10)
    (tmp_path / 'compile.log').write_text(compile_result.stdout + compile_result.stderr)
    assert compile_result.returncode == 0
    run = subprocess.run(['vvp', str(tmp_path / 'sim.vvp')], capture_output=True, text=True, timeout=10)
    (tmp_path / 'simulation.log').write_text(run.stdout + run.stderr)
    assert run.returncode == 0 and 'checks=33120 NOT_XSIM_REPRODUCTION' in run.stdout


def test_full_script_completion_ports_and_registered_receipt(tmp_path):
    """Extra read-only witness on the unchanged seven-context scripted stimulus."""
    top = a.actual_bench()
    assert top.count('endmodule') == 1
    extra = '''
  integer declaration_checks=0,declaration_idle=0;
  reg declaration_previous_running,declaration_previous_accept;
  always @(posedge fft_clk)begin
    declaration_previous_running=dut.retained.island.fast_running;
    declaration_previous_accept=dut.retained.island.completion_accept;
    #0.001;
    if(dut.retained.island.fast_running)begin
      if(dut.retained.island.completion_accept!==dut.retained.island.cutover.producer_closed)
        $fatal(1,"completion port disconnected");
      if(dut.retained.island.completion_accept!==0 && dut.retained.island.completion_accept!==1)
        $fatal(1,"completion net unknown");
      if(dut.retained.island.completion_receipt !==
         (declaration_previous_running ? declaration_previous_accept : 1'b0))
        $fatal(1,"completion receipt is not prior sampled net");
      if(dut.retained.island.state==dut.retained.island.RESET0 ||
         dut.retained.island.state==dut.retained.island.RESET1 ||
         dut.retained.island.state==dut.retained.island.WAIT_BANK)begin
        if(dut.retained.island.completion_accept!==0 || dut.retained.island.cutover.producer_closed!==0)
          $fatal(1,"startup/idle completion must be known zero");
        declaration_idle=declaration_idle+1;
      end
      declaration_checks=declaration_checks+1;
    end
  end
  final begin
    if(declaration_checks<10000||declaration_idle<100)$fatal(1,"declaration witness coverage");
    $display("DECLARATION_SCRIPT_WITNESS checks=%0d idle=%0d NOT_XSIM_REPRODUCTION",declaration_checks,declaration_idle);
  end
'''
    status = a.offline(tmp_path / 'run', execute=True, bench=top.replace('endmodule', extra + '\nendmodule'))
    assert status == {'compile': 0, 'service_executed': False, 'kind': 'OFFLINE_SCRIPT_NOT_FFT', 'script_exit': 0}
    log = (tmp_path / 'run/simulation.log').read_text()
    assert 'RACT_PASS contexts=7' in log and 'DECLARATION_SCRIPT_WITNESS checks=' in log
