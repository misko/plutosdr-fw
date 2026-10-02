#!/usr/bin/env python3
"""Bounded RX-only v0.59 four-rate / gain-mode scan regression matrix."""
import dataclasses,json,sys,time,os
from pathlib import Path
from pluto_plus.hardware.preflight import verify_metadata_runtime
verify_metadata_runtime(3)
import iio
from pluto_plus.adaptive_scan import ScanOutcome
from pluto_plus.adaptive_scan_campaign import build_adaptive_scan_setup,run_adaptive_scan_campaign
from pluto_plus.adaptive_scan_shadow import AdaptiveScanMode
from pluto_plus.models import GainMode

out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
c=iio.Context('ip:192.168.1.18')
serial='1040007c4a94000211000b009186843ef2'
assert c.attrs['hw_serial']==serial
assert c.attrs['fw_version']==os.environ.get('EXPECTED_FIRMWARE','v0.59-issue119-fastlock-rc2')
(out/'identity.json').write_text(json.dumps(dict(c.attrs),indent=2))
summary=[]
for rate in (2500000,5000000,7500000,10000000):
 for gain in (GainMode.MANUAL,GainMode.SLOW_ATTACK):
  rows=[]
  def observe(visit):
   row=dataclasses.asdict(visit.record)
   rows.append(row)
  setup=build_adaptive_scan_setup(session=time.time_ns()&0xffffffffffffffff,generation=1,seed=119,
      source_rate_hz=rate,analog_bandwidth_hz=rate,duration_ms=5000,dwell_ms=120,
      frequencies_hz=(959687498,1209687498,1459687498,1709687500),
      baseline_weights=(1,1,1,1),analysis_digest=b'\x77'*32,rx_mask=3,variable_dwell=True)
  stem=f'{rate}-{gain.value}'
  try:
   receipt=run_adaptive_scan_campaign('ip:192.168.1.18',serial,setup,lambda visit:ScanOutcome.QUIET,
      mode=AdaptiveScanMode.ADAPTIVE,manual_gain_db=30,gain_mode=gain,samples_per_block=1000000,
      visit_sink=observe)
  except Exception as exc:
   (out/(stem+'-failure.json')).write_text(json.dumps({'error':str(exc),'visits':rows},indent=2,default=str))
   raise
  body=dataclasses.asdict(receipt)
  (out/(stem+'.json')).write_text(json.dumps({'receipt':body,'visits':rows},indent=2,default=lambda v:v.hex() if isinstance(v,bytes) else str(v)))
  terminal=body['terminal']
  assert body['run']['gate']['passed'],body['run']['gate']
  assert terminal['state']==1 and terminal['flags']&1,terminal
  assert terminal['error']==0 and terminal['invalid']==0 and terminal['skipped']==0 and terminal['cancelled']==0,terminal
  assert terminal['delivered']>0 and terminal['delivered']==terminal['planned'],terminal
  assert body['restoration']['fastlock_inactive']
  result={'rate':rate,'gain_mode':gain.value,'delivered':terminal['delivered'],'gate':body['run']['gate'],'terminal':terminal,'restoration':body['restoration']}
  summary.append(result);print(json.dumps(result,default=str),flush=True)
(out/'summary.json').write_text(json.dumps(summary,indent=2,default=str))
