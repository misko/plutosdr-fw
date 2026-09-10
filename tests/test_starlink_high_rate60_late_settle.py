"""Testbench clock-only settling proof. No DUT/native/vendor execution."""

import re
import subprocess

import pytest

from tests.starlink_oracle.high_rate60_late import LOGIC, ROOT, check_recipe
from tests.starlink_oracle.high_rate60_late_bundle import check_logic
from tests.starlink_oracle.native60_budget import encoded, sha

CONTROL=10_000_000
HALF=5_000_000


def settling(event_fs):
    """Exact quantized100MHz control labels, strict future falling edges."""
    assert event_fs%CONTROL not in (0,HALF)  # Actual source avoids scheduling ties.
    anchor=(event_fs+HALF)//CONTROL
    old_eighth=event_fs//CONTROL+8
    corrected=max(old_eighth,anchor+8)
    return anchor,old_eighth,corrected


def test_every_actual_source_rise_fall_phase_through_watchdog():
    r=check_recipe(); counts={7:0,8:0}; checked=0
    for first in [10_433_333,18_766_666]:
        for event in range(first,r["global_control_watchdog"]*CONTROL,16_666_666):
            anchor,old,corrected=settling(event)
            counts[old-anchor]+=1; checked+=1
            assert old-anchor in (7,8) and corrected-anchor==8
            assert corrected-old in (0,1)
            assert event < corrected*CONTROL <= event+9*CONTROL
    assert checked==191999 and all(counts.values())
    # Actual original first and second anchors, reconstructed from immutable
    # oscillator/source coordinates, not adjusted receipt labels.
    assert settling(135_577_094_577)==(13558,13565,13566)
    assert settling(324_152_087_034)==(32415,32423,32423)
    # Correcting the pre-audit scheduling does not add work to the separately
    # timed snapshot body. One extra edge fits the predeclared entry slack.
    assert 512+34*24==r["snapshot_audit_limit_control_cycles"]==1328
    assert 8+1+1328+32 <= r["source_off_negative_limit_control_cycles"]==2048


def test_only_two_explicit_deadline_guards_change_original_logic():
    actual=(ROOT/LOGIC).read_text()
    old="""    wait(late_handshakes==1); repeat(8) @(negedge clk); late_snapshot(1);
    wait(source_finished && coarse_stopped && map_retained); repeat(8) @(negedge clk); late_snapshot(2);
"""
    new="""    wait(late_handshakes==1); repeat(8) @(negedge clk);
    // Eight falling edges can span only seven labels after a sample-domain
    // event. Preserve those edges, then meet the ORIGINAL >=8-label bound.
    while(cycles-late_handshake_cycle<8) @(negedge clk);
    late_snapshot(1);
    wait(source_finished && coarse_stopped && map_retained); repeat(8) @(negedge clk);
    while(cycles-source_off_cycle<8) @(negedge clk);
    late_snapshot(2);
"""
    assert actual.count(new)==1
    # Full byte identity is pinned to the original b31f bundle / HDL813f9eb1;
    # no Git objects or unfrozen filesystem dependency needed by this proof.
    original=actual.replace(new,old)
    assert original.count(old)==1
    assert sha(original.encode())=="b3a059c7f397eba2354eefc366bd6a799e3b1228cac8e9af2429f7e242bfbda1"


def test_original_acceptance_recipe_parser_and_context_adapter_unchanged():
    pins={"tests/starlink_oracle/high_rate60_late_result.py":"2cc2976c703f427450cc5479b937f90e9026c12881f5fce925061c90f34b4572",
          "tests/starlink_oracle/high_rate60_late_recipe.py":"7aaf5424dd06ff57f3a63050890ddd477cc5ef2ec99f1944ee4231c3a33b5f16",
          "tests/starlink_oracle/high_rate60_late.py":"2b44823404ad5017068ad59218f993c1438ce50ae6fb46a15b5693d05654782c"}
    for name,digest in pins.items(): assert sha((ROOT/name).read_bytes())==digest


@pytest.mark.parametrize("anchor",["late_handshake_cycle","source_off_cycle"])
@pytest.mark.parametrize("kind",["missing","other_anchor","short7","long9"])
def test_each_anchor_guard_mutation_rejected(tmp_path,anchor,kind):
    p=tmp_path/LOGIC; p.parent.mkdir(parents=True)
    loop=f"while(cycles-{anchor}<8) @(negedge clk);"
    alternative={"missing":"", "other_anchor":loop.replace(anchor,"wrong_anchor"),
                 "short7":loop.replace("<8","<7"),"long9":loop.replace("<8","<9")}[kind]
    p.write_text((ROOT/LOGIC).read_text().replace(loop,alternative))
    with pytest.raises(ValueError): check_logic(tmp_path)


@pytest.mark.parametrize("anchor",["late_handshake_cycle","source_off_cycle"])
def test_actual_stimulus_clock_only_phase_reproduction(tmp_path,anchor):
    source=(ROOT/LOGIC).read_text()
    loop=f"while(cycles-{anchor}<8) @(negedge clk);"
    assert source.count(loop)==1
    phases=[1,4_999_999,5_000_001,9_999_999,433_333,7_099_999,3_766_665,
            8_766_666,5_433_332,2_099_998,7_094_577,2_087_034]
    calls="\n".join(f"    probe({n});" for n in phases)
    # Pure observer reproduction: no design modules, hierarchy accesses, native
    # job or FFT. The corrected loop is copied literally from the frozen source.
    sv="""`timescale 1ns/1fs
module settle_unit;
  reg clk=0; always #5 clk=!clk;
  integer cycles=0,late_handshake_cycle=0,source_off_cycle=0;
  integer tested=0,old7=0,old8=0;
  always @(posedge clk) cycles=cycles+1;
  task automatic probe(input integer phase_fs);
    integer anchor_cycle,old_cycle,new_cycle;
    begin
      @(negedge clk); #(phase_fs/1000000.0);
      anchor_cycle=cycles; late_handshake_cycle=cycles; source_off_cycle=cycles;
      fork
        begin repeat(8) @(negedge clk); old_cycle=cycles; end
        begin repeat(8) @(negedge clk);
          LOOP
          new_cycle=cycles;
        end
      join
      if(old_cycle-anchor_cycle==7) old7=old7+1;
      else if(old_cycle-anchor_cycle==8) old8=old8+1;
      else $fatal(1,"old phase relation");
      if(new_cycle-anchor_cycle!=8 || new_cycle<old_cycle || new_cycle-old_cycle>1)
        $fatal(1,"corrected schedule violates unchanged8 deadline");
      tested=tested+1;
      $display("SETTLE_PHASE phase_fs=%0d old_labels=%0d new_labels=%0d",phase_fs,old_cycle-anchor_cycle,new_cycle-anchor_cycle);
    end
  endtask
  initial begin
CALLS
    if(tested!=12 || !old7 || !old8) $fatal(1,"phase coverage");
    $display("SETTLE_UNIT_PASS cases=12 NO_DUT_NATIVE_OR_FFT"); $finish;
  end
endmodule
""".replace("LOOP",loop).replace("CALLS",calls)
    p=tmp_path/"settle_unit.sv"; p.write_text(sv)
    compiled=subprocess.run(["iverilog","-g2012","-s","settle_unit","-o",str(tmp_path/"unit.vvp"),str(p)],capture_output=True,text=True,check=False,timeout=30)
    assert compiled.returncode==0,compiled.stderr
    ran=subprocess.run(["vvp",str(tmp_path/"unit.vvp")],capture_output=True,text=True,check=False,timeout=30)
    (tmp_path/"unit.log").write_text(ran.stdout+ran.stderr)
    (tmp_path/"receipt.json").write_bytes(encoded({"compile_exit":compiled.returncode,"unit_exit":ran.returncode,
        "source_sha256":sha(sv.encode()),"logic_sha256":sha(source.encode()),"native_service":False,"vendor_fft":False}))
    assert ran.returncode==0 and ran.stdout.count("SETTLE_UNIT_PASS")==1
    assert not re.search("fatal|error|fail",ran.stdout+ran.stderr,re.IGNORECASE)
    rows=re.findall(r"SETTLE_PHASE phase_fs=(\d+) old_labels=(\d+) new_labels=(\d+)",ran.stdout)
    assert rows==[(str(n),str(settling(n)[1]-settling(n)[0]),"8") for n in phases]
