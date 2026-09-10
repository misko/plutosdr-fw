"""Bounded collector protocol: retain-before-POP, no uncertain resubmission."""
import errno
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from tools import starlink_glrt_schedule_capture as capture
from tools.starlink_glrt_iio import Device
from tools.starlink_glrt_schedule_abi import MAGIC, RATE, SAMPLES, ScheduleBatch


def text(prefix, words):
    return prefix+" 00010000 "+" ".join(f"{v:08x}" for v in words)


class Radio:
    def __init__(self, root, fault=None):
        self.root=root; self.fault=fault; self.commands=[]; self.epoch=2; self.generation=0
        self.batch=None; self.popped=0; self.reads=0; self.closed=False
        self.attributes={"hw_serial":capture.SERIAL,"fw_version":"scheduled-test"}

    def device(self,name):
        assert name == "starlink-glrt-iq"
        return self

    def close(self): self.closed=True

    def read(self,name):
        if name == "capture_abi": return capture.BASE_ABI
        if name == "native_schedule_abi": return "none" if self.fault=="abi" else "GLS1-1.0"
        if name == "native_capture_enable": return "0"
        if name == "native_schedule_snapshot":
            self.generation+=1
            configured=self.batch.repeats if self.batch else 0
            missing=int(bool(configured) and self.fault=="loss")
            admitted=configured-missing
            queued=admitted-self.popped
            index=2**55+1000
            return text("GLS1SNAP",[MAGIC,self.generation,self.epoch,index%2**32,index>>32,
                16 | (4 if queued else 0),0,configured,admitted,0,missing,0,0,0,
                admitted,self.popped,queued,admitted,0,0])
        if name == "native_schedule_result":
            self.reads+=1
            if self.batch is None: raise OSError(errno.EAGAIN,"empty")
            start,step=self.batch.prediction(self.popped)
            w=[MAGIC,self.popped,self.batch.tag,start%2**32,start>>32,self.batch.seed,step,SAMPLES,0]
            w += [0]*16+[RATE,SAMPLES,self.popped,0,0,0,0]
            if self.fault=="corrupt": w[28]=1
            if self.fault=="stale": w[2]+=1
            if self.fault=="changed" and self.reads%2==0: w[5]+=1
            return text("GLS1",[self.epoch]+w)
        raise AssertionError(name)

    def command(self,name,value):
        self.commands.append((name,value))
        if name == "native_schedule_command":
            if value==4:
                assert self.batch is None or self.popped==self.batch.repeats
                self.batch=None; self.popped=0
            elif value==16: self.epoch+=1
            elif value==2: pass
            else: raise AssertionError(value)
        elif name == "native_schedule_submit":
            self.batch=ScheduleBatch(*(int(w,16) for w in value.split()))
            if self.fault=="uncertain": raise OSError(errno.EIO,"uncertain SUBMIT")
        elif name == "native_schedule_pop":
            assert [int(w,16) for w in value.split()] == [self.epoch,self.popped]
            # A raw record must already be retained when retirement is issued.
            paths=list(self.root.rglob(f"result-{self.popped:04d}.txt"))
            assert any(f"{self.batch.tag:08x}" in p.read_text() for p in paths)
            self.popped+=1
        else: raise AssertionError(name)


def run(radio,root,clock=lambda:0):
    return capture.run_batch(radio,root,tag=19,repeats=32,phase_seed=17,phase_step=7310173,
        step_delta_q16=65536,lead_samples=1200000,deadline=60,clock=clock,sleep=lambda _:None)


def test_finite_750_hz_batch_retains_all_heads_before_acknowledging(tmp_path):
    radio=Radio(tmp_path)
    result=run(radio,tmp_path/"batch")
    assert result["status"] == "transport_pass" and result["repeats"] == 32
    assert result["last_start"]-result["first_start"] == 31*80000
    assert result["high_water"] == 32 and result["terminal_snapshot"]["queued"] == 0
    assert len(list((tmp_path/"batch").glob("result-*.txt"))) == 32
    assert sum(name=="native_schedule_submit" for name,_ in radio.commands) == 1
    assert sum(name=="native_schedule_pop" for name,_ in radio.commands) == 32


@pytest.mark.parametrize("fault", ["corrupt","stale","changed","uncertain"])
def test_failed_or_uncertain_evidence_is_never_popped_or_resubmitted(tmp_path,fault):
    radio=Radio(tmp_path,fault)
    with pytest.raises((OSError,ValueError)):
        run(radio,tmp_path/"batch")
    assert not any(name=="native_schedule_pop" for name,_ in radio.commands)
    assert sum(name=="native_schedule_submit" for name,_ in radio.commands) == 1
    assert (tmp_path/"batch/descriptor.json").exists()
    if fault != "uncertain":
        assert (tmp_path/"batch/result-0000.txt").exists()


def test_explicit_missing_repeat_does_not_become_a_passing_transport_test(tmp_path):
    radio=Radio(tmp_path,"loss")
    with pytest.raises(ValueError,match="lost"):
        run(radio,tmp_path/"batch")
    assert radio.popped==31
    assert len(list((tmp_path/"batch").glob("result-*.txt")))==31


def test_elapsed_deadline_prevents_any_radio_write(tmp_path):
    radio=Radio(tmp_path)
    with pytest.raises(TimeoutError): run(radio,tmp_path/"batch",clock=lambda:61)
    assert radio.commands==[]


def args(root):
    return Namespace(uri=capture.URI,serial=capture.SERIAL,firmware_version="scheduled-test",
        output=root,tag=20,phase_seed=17,phase_step=7310173,step_delta_q16=65536,
        lead_samples=1200000,lo_hz=1690312496,bandwidth_hz=2500000,libiio=None)


def setup(monkeypatch,tmp_path,fault=None):
    radio=Radio(tmp_path,fault)
    monkeypatch.setattr(capture,"radio_state",lambda _:dict(sample_rate_hz=RATE,tx_powerdown=1,
        rx_lo_hz=1690312496,rf_bandwidth_hz=2500000))
    return radio


def test_complete_canary_runs_two_generations_and_cleans_up_without_rf_changes(monkeypatch,tmp_path):
    radio=setup(monkeypatch,tmp_path)
    result=capture.collect(args(tmp_path/"capture"),library=object(),context_factory=lambda *a,**kw:radio)
    assert result["status"]=="transport_pass" and result["failures"]==[]
    assert [b["repeats"] for b in result["batches"]]==[32,64]
    assert [b["epoch"] for b in result["batches"]]==[3,4]
    assert radio.closed and radio.batch is None
    assert result["radio_before"]==result["radio_after"]
    protocol=json.loads((tmp_path/"capture/protocol.json").read_text())
    assert protocol["maximum_collection_seconds"]==60 and protocol["precision_qualified"] is False


def test_wrong_profile_causes_no_mutation(monkeypatch,tmp_path):
    radio=setup(monkeypatch,tmp_path,"abi")
    result=capture.collect(args(tmp_path/"capture"),library=object(),context_factory=lambda *a,**kw:radio)
    assert result["status"]=="failed" and radio.closed and not radio.commands


def test_capture_failure_cancels_future_work_but_preserves_unacknowledged_head(monkeypatch,tmp_path):
    radio=setup(monkeypatch,tmp_path,"corrupt")
    result=capture.collect(args(tmp_path/"capture"),library=object(),context_factory=lambda *a,**kw:radio)
    assert result["status"]=="failed" and radio.closed
    assert ("native_schedule_command",2) in radio.commands
    assert radio.popped==0 and radio.batch is not None
    assert sum(name=="native_schedule_command" and v==4 for name,v in radio.commands)==1
    assert any("cleanup" in failure for failure in result["failures"])


def test_iio_command_never_attempts_readback_of_write_only_attribute():
    device=object.__new__(Device); device.pointer=7
    writes=[]
    device._write=lambda p,n,v:writes.append((p,n,v)) or len(v)
    device._read=lambda *args:pytest.fail("readback of write-only command")
    device.command("native_schedule_command",16)
    assert writes==[(7,b"native_schedule_command",b"16")]
    device._write=lambda *args:-errno.EBUSY
    with pytest.raises(OSError) as error: device.command("native_schedule_command",4)
    assert error.value.errno==errno.EBUSY


@pytest.mark.parametrize("entry", [["tools/starlink_glrt_schedule_capture.py"],
                                   ["-m","tools.starlink_glrt_schedule_capture"]])
def test_collector_entry_point_loads_without_opening_a_radio(entry):
    result=subprocess.run([sys.executable,*entry,"--help"],cwd=Path(__file__).resolve().parents[2],
                          capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    assert "--firmware-version" in result.stdout
