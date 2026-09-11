"""Independent transaction model of the staged command/response contract."""
from pathlib import Path
import random
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'hdl/library/starlink_pss_acquisition/staged_control/starlink_pss_descriptor_commands.v'
D=70

def command(**kw):
    value=dict(reset=1,abort=0,valid=0,op=0,tag=0,desc=0,ready=1,lookup=0,query=0)
    value.update(kw);return value

class Model:
    def __init__(self,width):self.width=width;self.reset()
    def reset(self):
        self.entries={};self.next=0;self.exhausted=False;self.poison=False
        self.pending=None;self.response=None;self.last_response=(0,0)
    def fault(self,c):
        return bool(c['reset'] and (self.poison or c['abort'] or (self.pending is not None and not self.pending['good'])))
    def ready(self,c):
        return bool(c['reset'] and not c['abort'] and not self.poison and self.pending is None and self.response is None and
                    (c['op']!=0 or (len(self.entries)<2 and not self.exhausted)))
    def observe(self,c):
        live=c['reset'] and not self.fault(c)
        found=bool(live and c['lookup'] and c['query'] in self.entries)
        entry=self.entries[c['query']] if found else None
        occupied=sum(1<<e['slot'] for e in self.entries.values())
        committed=sum(1<<e['slot'] for e in self.entries.values() if e['done']) if live else 0
        return [(1,int(self.ready(c))),(1,int(live and self.response is not None)),
                (2,self.last_response[0]),(self.width,self.last_response[1]),(1,int(self.fault(c))),
                (2,occupied),(2,committed),(1,int(self.exhausted)),(1,int(found)),
                (1,int(found and entry['done'])),(D,entry['descriptor'] if found else 0)]
    def step(self,c):
        if not c['reset']:self.reset();return
        if c['abort'] or self.poison:
            self.poison=True;self.pending=None;self.response=None;return
        accepts=self.ready(c) and c['valid']
        if self.response is not None and c['ready']:self.response=None
        if self.pending is not None:
            p=self.pending;self.pending=None
            if not p['good']:self.poison=True;self.response=None;return
            if p['op']==0:
                self.entries[p['tag']]=dict(slot=p['slot'],descriptor=p['desc'],done=False)
                if self.next==(1<<self.width)-1:self.exhausted=True
                else:self.next+=1
            elif p['op']==1:self.entries[p['tag']]['done']=True
            else:del self.entries[p['tag']]
            self.last_response=(p['op'],p['tag']);self.response=self.last_response
        elif accepts:
            op,tag=c['op'],c['tag'];good=False;slot=0
            if op==0:
                slot=next(s for s in (0,1) if all(e['slot']!=s for e in self.entries.values()))
                tag=self.next;good=True
            elif op in (1,2) and tag in self.entries:
                good=self.entries[tag]['done']==(op==2);slot=self.entries[tag]['slot']
            self.pending=dict(op=op,tag=tag,slot=slot,good=good,desc=c['desc'])

def pack(fields):
    value=0
    for width,v in fields:
        assert 0<=v<1<<width
        value=(value<<width)|v
    return value

def simulate(tmp_path,width,commands):
    model=Model(width);vectors=[]
    for c in commands:
        if not c['reset']:model.reset()
        before=model.observe(c);model.step(c);after=model.observe(c)
        fields=[(1,c['reset']),(1,c['abort']),(1,c['valid']),(2,c['op']),(width,c['tag']),
                (D,c['desc']),(1,c['ready']),(1,c['lookup']),(width,c['query'])]
        vectors.append(pack(fields+before+after))
    path=tmp_path/'vectors.mem';path.write_text(''.join(f'{v:x}\n' for v in vectors))
    bench=tmp_path/'bench.sv'
    bench.write_text('''`timescale 1ns/1ps
module tb;
localparam D=70,T='''+str(width)+''',E=T+D+12,W=3*D+4*T+31,N='''+str(len(vectors))+''';
reg clk=0;always #5 clk=~clk;
reg resetn=0,abort_epoch=0,command_valid=0,response_ready=1,lookup_valid=0;
reg [1:0] command_opcode=0;
reg [T-1:0] command_tag=0,lookup_tag=0;
reg [D-1:0] command_descriptor=0;
wire command_ready,response_valid,lookup_found,lookup_committed,tags_exhausted,fault;
wire [1:0] response_opcode,occupied,committed;
wire [T-1:0] response_tag;
wire [D-1:0] lookup_descriptor;
starlink_pss_descriptor_commands #(.TAG_WIDTH(T)) dut(.*);
wire [E-1:0] observed={command_ready,response_valid,response_opcode,response_tag,fault,occupied,committed,tags_exhausted,lookup_found,lookup_committed,lookup_descriptor};
reg [W-1:0] vectors[0:N-1];reg [E-1:0] expected_before,expected_after;integer row;
initial begin
  $readmemh("'''+str(path)+'''",vectors);
  for(row=0;row<N;row=row+1) begin
    @(negedge clk);
    {resetn,abort_epoch,command_valid,command_opcode,command_tag,command_descriptor,response_ready,lookup_valid,lookup_tag,expected_before,expected_after}=vectors[row];
    #1;if(observed!==expected_before) $fatal(1,"PRE row=%0d actual=%h expected=%h",row,observed,expected_before);
    @(posedge clk);#0.1;
    if(observed!==expected_after) $fatal(1,"POST row=%0d actual=%h expected=%h",row,observed,expected_after);
  end
  $display("COMMANDS_PASS rows=%0d",N);$finish(0);
end
endmodule
''')
    p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(tmp_path/'sim'),str(RTL),str(bench)],capture_output=True,text=True,timeout=30)
    (tmp_path/'compile.log').write_text(p.stdout+p.stderr)
    assert p.returncode==0,p.stdout+p.stderr
    p=subprocess.run(['vvp',str(tmp_path/'sim')],capture_output=True,text=True,timeout=30)
    (tmp_path/'run.log').write_text(p.stdout+p.stderr)
    assert p.returncode==0,p.stdout+p.stderr
    assert p.stdout.splitlines()==[f'COMMANDS_PASS rows={len(vectors)}']

def transaction(op=0,tag=0,desc=0):
    return [command(valid=1,op=op,tag=tag,desc=desc),command(),command()]

def test_exact_command_latency_and_response_backpressure(tmp_path):
    seq=[command(reset=0),command(valid=1,desc=123),command(ready=0)]
    seq += [command(valid=1,op=1,tag=0,ready=0,lookup=1,query=0)]*20
    seq += [command(valid=1,op=1,tag=0),command(valid=1,op=1,tag=0),command(),command()]
    seq += transaction(desc=456)+[command(lookup=1,query=0),command(lookup=1,query=1)]
    seq += transaction(op=2,tag=0)+transaction(op=1,tag=1)+transaction(op=2,tag=1)
    simulate(tmp_path,32,seq)

@pytest.mark.parametrize('stage',['validate','response','two_owned'])
@pytest.mark.parametrize('cancel',['abort','reset'])
def test_cancel_never_leaks_a_late_response(tmp_path,stage,cancel):
    seq=[command(reset=0),command(valid=1,desc=123)]
    if stage=='response':seq += [command(ready=0)]
    elif stage=='two_owned':seq += [command(),command()]+transaction(desc=456)
    seq += [command(abort=1) if cancel=='abort' else command(reset=0)]
    seq += [command(lookup=1,query=0)]*5
    seq += [command(reset=0)]+transaction(desc=789)+transaction(op=1,tag=0)
    simulate(tmp_path,32,seq)

@pytest.mark.parametrize('bad',['unowned_commit','uncommitted_release','duplicate_commit','duplicate_release','stale_tag','opcode'])
def test_invalid_commands_cannot_succeed(tmp_path,bad):
    seq=[command(reset=0)]+transaction(desc=123)
    if bad=='unowned_commit':seq+=transaction(op=1,tag=77)
    elif bad=='uncommitted_release':seq+=transaction(op=2,tag=0)
    elif bad=='duplicate_commit':seq+=transaction(op=1,tag=0)+transaction(op=1,tag=0)
    elif bad=='duplicate_release':seq+=transaction(op=1,tag=0)+transaction(op=2,tag=0)+transaction(op=2,tag=0)
    elif bad=='stale_tag':seq+=transaction(op=1,tag=0)+transaction(op=2,tag=0)+transaction(desc=456)+transaction(op=1,tag=0)
    else:seq+=transaction(op=3)
    seq += [command(valid=1,desc=999,lookup=1,query=0)]*5
    simulate(tmp_path,32,seq)

@pytest.mark.parametrize('width',[1,2,4])
def test_exhaustion_blocks_without_wrap(tmp_path,width):
    seq=[command(reset=0)]
    for tag in range(1<<width):seq+=transaction(desc=tag)+transaction(op=1,tag=tag)+transaction(op=2,tag=tag)
    seq += [command(valid=1,desc=999)]*8
    simulate(tmp_path,width,seq)

def test_every_descriptor_and_identity_bit(tmp_path):
    seq=[command(reset=0)]
    for tag in range(70):
        seq+=transaction(desc=1<<tag)+[command(lookup=1,query=tag)]
        seq+=transaction(op=1,tag=tag)+transaction(op=2,tag=tag)
    for bit in range(32):
        seq+=[command(reset=0)]+transaction(desc=123)+transaction(op=1,tag=1<<bit)
    simulate(tmp_path,32,seq)

@pytest.mark.parametrize('seed',[7,101,9911])
def test_random_ready_valid_scoreboard(tmp_path,seed):
    rng=random.Random(seed);m=Model(32);seq=[command(reset=0)];request=None
    for tick in range(3000):
        c=command(ready=int(rng.randrange(4)!=0))
        if tick%251==250:c['abort']=1;request=None
        elif m.poison:c['reset']=0;request=None
        else:
            if request is None and rng.randrange(2):
                options=[]
                if len(m.entries)<2 and not m.exhausted:options.append(dict(valid=1,op=0,desc=rng.getrandbits(D)))
                for tag,e in m.entries.items():options.append(dict(valid=1,op=2 if e['done'] else 1,tag=tag))
                # Choose new work only at an idle controller boundary; no
                # already-pending commit is accidentally reissued as a new job.
                if options and m.pending is None and m.response is None:request=rng.choice(options)
            if request:c.update(request)
            if m.entries:c.update(lookup=1,query=rng.choice(list(m.entries)))
        accepted=m.ready(c) and c['valid'];seq.append(c);m.step(c)
        if accepted:request=None
    simulate(tmp_path,32,seq)
