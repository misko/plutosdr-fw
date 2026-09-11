"""Transaction-model RTL checks for the new ownership table, not a receiver test."""
from pathlib import Path
import random
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_descriptor_slots.v'
D = 70

def pack(fields):
    value = 0
    for width, field in fields:
        assert 0 <= field < 1 << width
        value = (value << width) | field
    return value

class Model:
    def __init__(self, width):
        self.width = width
        self.reset()

    def reset(self):
        self.entries = {}
        self.next = 0
        self.exhausted = False
        self.poisoned = False

    def error(self, c):
        return bool(c['abort'] or
            (c['cv'] and (c['ct'] not in self.entries or self.entries[c['ct']]['committed'])) or
            (c['rv'] and (c['rt'] not in self.entries or not self.entries[c['rt']]['committed'])))

    def observe(self, c):
        fault = bool(c['reset'] and (self.poisoned or self.error(c)))
        live = bool(c['reset'] and not fault)
        occupied = sum(1 << e['slot'] for e in self.entries.values())
        committed = sum(1 << e['slot'] for e in self.entries.values() if e['committed']) if live else 0
        found = bool(live and c['lv'] and c['lt'] in self.entries)
        entry = self.entries[c['lt']] if found else None
        return pack([(1,int(live and not self.exhausted and len(self.entries)<2)),
                     (self.width,self.next),(1,int(fault)),(2,occupied),(2,committed),
                     (1,int(self.exhausted)),(1,int(found)),(1,int(found and entry['committed'])),
                     (D,entry['descriptor'] if found else 0)])

    def step(self, c):
        if not c['reset']:
            self.reset()
            return
        if self.poisoned or self.error(c):
            self.poisoned = True
            return
        free = [s for s in (0,1) if all(e['slot'] != s for e in self.entries.values())]
        if c['cv']:
            self.entries[c['ct']]['committed'] = True
        if c['rv']:
            del self.entries[c['rt']]
        if c['av'] and free and not self.exhausted:
            self.entries[self.next] = dict(slot=free[0],descriptor=c['desc'],committed=False)
            if self.next == (1 << self.width)-1:
                self.exhausted = True
            else:
                self.next += 1

def command(**overrides):
    c = dict(reset=1,abort=0,av=0,desc=0,cv=0,ct=0,rv=0,rt=0,lv=0,lt=0)
    c.update(overrides)
    return c

def simulate(tmp_path, width, commands):
    model = Model(width)
    words = []
    for c in commands:
        if not c['reset']:
            model.reset()
        before = model.observe(c)
        model.step(c)
        quiet = dict(c,abort=0,av=0,cv=0,rv=0)
        after = model.observe(quiet)
        ewidth = width+D+9
        words.append(pack([(1,c['reset']),(1,c['abort']),(1,c['av']),(D,c['desc']),
                           (1,c['cv']),(width,c['ct']),(1,c['rv']),(width,c['rt']),
                           (1,c['lv']),(width,c['lt']),(ewidth,before),(ewidth,after)]))
    vectors = tmp_path/'vectors.mem'
    vectors.write_text(''.join(f'{v:x}\n' for v in words))
    bench = tmp_path/'bench.sv'
    bench.write_text('''`timescale 1ns/1ps
module tb;
localparam D=70, T='''+str(width)+''', E=T+D+9, W=3*D+5*T+24, N='''+str(len(words))+''';
reg clk=0;
always #5 clk=~clk;
reg resetn=0,abort_epoch=0,allocate_valid=0,commit_valid=0,release_valid=0,lookup_valid=0;
reg [D-1:0] allocate_descriptor=0;
reg [T-1:0] commit_tag=0,release_tag=0,lookup_tag=0;
wire allocate_ready,fault,lookup_found,lookup_committed,tags_exhausted;
wire [T-1:0] allocate_tag;
wire [D-1:0] lookup_descriptor;
wire [1:0] occupied,committed;
starlink_pss_descriptor_slots #(.TAG_WIDTH(T)) dut(.*);
wire [E-1:0] observed={allocate_ready,allocate_tag,fault,occupied,committed,tags_exhausted,lookup_found,lookup_committed,lookup_descriptor};
reg [W-1:0] vectors[0:N-1];
reg [E-1:0] expected_before,expected_after;
integer row;
initial begin
  $readmemh("'''+str(vectors)+'''",vectors);
  for(row=0;row<N;row=row+1) begin
    @(negedge clk);
    {resetn,abort_epoch,allocate_valid,allocate_descriptor,commit_valid,commit_tag,release_valid,release_tag,lookup_valid,lookup_tag,expected_before,expected_after}=vectors[row];
    #1;
    if(observed!==expected_before) $fatal(1,"PRE row=%0d actual=%h expected=%h",row,observed,expected_before);
    @(posedge clk);#0.1;
    abort_epoch=0;allocate_valid=0;commit_valid=0;release_valid=0;
    #0.1;
    if(observed!==expected_after) $fatal(1,"POST row=%0d actual=%h expected=%h",row,observed,expected_after);
  end
  $display("SLOTS_PASS rows=%0d",N);$finish(0);
end
endmodule
''')
    compile = subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(RTL),str(bench)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(compile.stdout+compile.stderr)
    assert compile.returncode == 0, compile.stdout+compile.stderr
    run = subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'run.log').write_text(run.stdout+run.stderr)
    assert run.returncode == 0, run.stdout+run.stderr
    assert run.stdout.splitlines() == [f'SLOTS_PASS rows={len(words)}']

def test_two_live_jobs_backpressure_and_independent_release(tmp_path):
    seq = [command(reset=0),command(av=1,desc=123),command(av=1,desc=(1<<69)+987),command(lv=1,lt=0)]
    seq += [command(av=1,desc=999,lv=1,lt=1)]*20
    seq += [command(cv=1,ct=0), command(cv=1,ct=1,rv=1,rt=0),
            command(av=1,desc=555,lv=1,lt=1), command(lv=1,lt=2),
            command(rv=1,rt=1,cv=1,ct=2),command(rv=1,rt=2),command(lv=1,lt=0)]
    simulate(tmp_path,32,seq)

@pytest.mark.parametrize('event', ['release_uncommitted','duplicate_commit','duplicate_release','stale_commit','abort'])
def test_bad_event_quarantines_without_public_authority(tmp_path,event):
    seq = [command(reset=0),command(av=1,desc=123),command(cv=1,ct=0)]
    if event=='release_uncommitted':
        seq += [command(av=1,desc=456),command(rv=1,rt=1)]
    elif event=='duplicate_commit':seq += [command(cv=1,ct=0)]
    elif event=='duplicate_release':seq += [command(rv=1,rt=0),command(rv=1,rt=0)]
    elif event=='stale_commit':seq += [command(rv=1,rt=0),command(av=1,desc=456),command(cv=1,ct=0)]
    else:seq += [command(abort=1)]
    seq += [command(av=1,desc=999,lv=1,lt=0)]*8
    seq += [command(reset=0),command(av=1,desc=678),command(cv=1,ct=0,lv=1,lt=0),command(rv=1,rt=0)]
    simulate(tmp_path,32,seq)

@pytest.mark.parametrize('width',[1,2,4])
def test_tag_exhaustion_never_reuses_tag(tmp_path,width):
    seq = [command(reset=0)]
    for tag in range(1<<width):
        seq += [command(av=1,desc=tag+1),command(cv=1,ct=tag,lv=1,lt=tag),command(rv=1,rt=tag)]
    seq += [command(av=1,desc=777)]*8
    simulate(tmp_path,width,seq)

def test_full_descriptor_not_truncated(tmp_path):
    seq = [command(reset=0)]
    for tag,descriptor in enumerate([0,(1<<D)-1]+[1<<bit for bit in range(D)]):
        seq += [command(av=1,desc=descriptor),command(lv=1,lt=tag),
                command(cv=1,ct=tag,lv=1,lt=tag),command(rv=1,rt=tag)]
    simulate(tmp_path,32,seq)

@pytest.mark.parametrize('event',['commit','release'])
def test_every_tag_bit_participates_in_identity(tmp_path,event):
    seq=[]
    for bit in range(32):
        seq += [command(reset=0),command(av=1,desc=1),command(lv=1,lt=1<<bit)]
        if event=='commit':seq += [command(cv=1,ct=1<<bit)]
        else:seq += [command(cv=1,ct=0),command(rv=1,rt=1<<bit)]
        seq += [command(lv=1,lt=0)]
    simulate(tmp_path,32,seq)

@pytest.mark.parametrize('seed',[7,101,9911])
def test_random_transaction_scoreboard(tmp_path,seed):
    rng = random.Random(seed)
    model = Model(32)
    seq = [command(reset=0)]
    for tick in range(3000):
        c = command()
        if tick%211==210:
            c['abort']=1
        elif model.poisoned:
            c['reset']=0
        else:
            owned = [t for t,e in model.entries.items() if not e['committed']]
            done = [t for t,e in model.entries.items() if e['committed']]
            if rng.randrange(3)==0:
                c.update(av=1,desc=rng.getrandbits(D))
            if owned and rng.randrange(3)==0:
                c.update(cv=1,ct=rng.choice(owned))
            if done and rng.randrange(3)==0:
                c.update(rv=1,rt=rng.choice(done))
            if model.entries and rng.randrange(2):
                c.update(lv=1,lt=rng.choice(list(model.entries)))
            else:
                c.update(lv=1,lt=model.next+1)
        seq.append(c)
        model.step(c)
    simulate(tmp_path,32,seq)

@pytest.mark.parametrize('change', ['early_release','ignore_tag','wrap','truncate','ignore_abort'])
def test_runtime_mutants_are_detected(tmp_path,monkeypatch,change):
    original = RTL.read_text()
    mutations = {
        'early_release': ('state0 == COMMITTED && release_tag === tag0', 'state0 != FREE && release_tag === tag0'),
        'ignore_tag': ('state0 == OWNED && commit_tag === tag0', 'state0 == OWNED'),
        'wrap': ("if (&next_tag) exhausted <= 1;", "if (&next_tag) next_tag <= 0;"),
        'truncate': ('descriptor0 <= allocate_descriptor;', "descriptor0 <= {1'b0, allocate_descriptor[DESCRIPTOR_WIDTH-2:0]};"),
        'ignore_abort': ('!commands_known || abort_epoch ||', '!commands_known ||'),
    }
    before, after = mutations[change]
    assert original.count(before) == 1
    mutant = tmp_path/'mutant.v'
    mutant.write_text(original.replace(before,after,1))
    monkeypatch.setattr(__import__(__name__,fromlist=['RTL']), 'RTL', mutant)
    if change=='early_release':seq=[command(reset=0),command(av=1,desc=1),command(rv=1,rt=0)]
    elif change=='ignore_tag':seq=[command(reset=0),command(av=1,desc=1),command(cv=1,ct=3)]
    elif change=='truncate':seq=[command(reset=0),command(av=1,desc=1<<69),command(lv=1,lt=0)]
    elif change=='ignore_abort':seq=[command(reset=0),command(av=1,desc=1),command(abort=1)]
    else:
        seq=[command(reset=0)]
        for tag in range(4):
            seq += [command(av=1,desc=1),command(cv=1,ct=tag),command(rv=1,rt=tag)]
        seq += [command(av=1,desc=2)]
    with pytest.raises(AssertionError):
        simulate(tmp_path,2,seq)
    assert 'FATAL' in (tmp_path/'run.log').read_text()

@pytest.mark.parametrize('value', ['x','z'])
@pytest.mark.parametrize('signal', ['allocate_valid','commit_valid','release_valid','abort_epoch','commit_tag','release_tag','lookup_valid','lookup_tag'])
def test_unknown_controls_fail_closed(tmp_path,signal,value):
    # Reuse declarations only; this is a separate four-state RTL exercise.
    simulate(tmp_path,4,[command(reset=0),command()])
    declarations=(tmp_path/'bench.sv').read_text().split('initial begin\n',1)[0]
    read_only = signal.startswith('lookup')
    extra = "commit_valid=1;" if signal=='commit_tag' else "release_valid=1;" if signal=='release_tag' else ''
    width = 4 if signal.endswith('_tag') else 1
    stimulus = f"{signal}={width}'b{value};"
    initial_commit = '' if signal=='commit_tag' else '''
  @(negedge clk);commit_valid=1;commit_tag=0;
  @(posedge clk);#0.1;commit_valid=0;
'''
    body = '''initial begin
  @(negedge clk);resetn=0;
  @(negedge clk);resetn=1;allocate_valid=1;allocate_descriptor=70'h123456789;
  @(posedge clk);#0.1;allocate_valid=0;
  '''+initial_commit+'''
  @(negedge clk);lookup_valid=1;lookup_tag=0;
  '''+extra+stimulus+'''
  #1;
  if(lookup_found!==0 || lookup_committed!==0) $fatal(1,"unknown input exposed descriptor");
  '''+('''if(fault!==0 || committed!==1) $fatal(1,"read-only miss changed ownership");''' if read_only else '''
  if(fault!==1 || allocate_ready!==0 || committed!==0) $fatal(1,"unknown command not fenced");
  @(posedge clk);#0.1;
  allocate_valid=0;commit_valid=0;release_valid=0;abort_epoch=0;lookup_valid=0;
  #0.1;if(fault!==1) $fatal(1,"unknown command not quarantined");
  ''')+'''
  $display("FOUR_STATE_PASS");$finish(0);
end
endmodule
'''
    bench=tmp_path/'four_state.sv';bench.write_text(declarations+body)
    compile=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'four_sim'),str(RTL),str(bench)],capture_output=True,text=True,timeout=30)
    (tmp_path/'four_compile.log').write_text(compile.stdout+compile.stderr)
    assert compile.returncode==0,compile.stderr
    run=subprocess.run(['vvp',str(tmp_path/'four_sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'four_run.log').write_text(run.stdout+run.stderr)
    assert run.returncode==0 and run.stdout.splitlines()==['FOUR_STATE_PASS'],run.stdout+run.stderr
