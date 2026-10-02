#!/usr/bin/env python3
"""Bounded four-profile TX2 loopback qualification of the deployed kernel API.

Requires the operator-confirmed attenuated TX2-to-both-RX fixture. SSH_WRAPPER
names a local executable accepting a remote command; it must provide credentials
without placing them in this script or its evidence. Run with the radio-hardware
venv and distro libiio Python bindings on PYTHONPATH.
"""
import os,sys,json,subprocess,time,select
from pathlib import Path
import iio,numpy as np
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
ssh=os.environ['SSH_WRAPPER']
c=iio.Context('ip:192.168.1.18');c.set_timeout(5000)
assert c.attrs['hw_serial']=='1040007c4a94000211000b009186843ef2'
assert c.attrs['fw_version']=='v0.54-issue119-fastlock-rc1'
p=c.find_device('ad9361-phy');tx=c.find_device('cf-ad9361-dds-core-lpc');rx=c.find_device('cf-ad9361-lpc')
lo=p.find_channel('altvoltage0',True);tlo=p.find_channel('altvoltage1',True)
dds=[tx.find_channel('altvoltage'+str(i),True) for i in range(8)]
saved=[];proc=None;rows=[];restoration_errors=[]
regs={a:tx.reg_read(a) for j in range(4) for a in (0x400+j*0x40,0x404+j*0x40,0x408+j*0x40,0x40c+j*0x40,0x414+j*0x40,0x418+j*0x40)}
profiles=[]
for j in range(4):
 lo.attrs['fastlock_save'].value=str(j);profiles.append(lo.attrs['fastlock_save'].value)
def persist_snapshot():
 (out/'snapshot.json').write_text(json.dumps({'attrs':[(ch.device.id,ch.id,ch.output,a,v) for ch,a,v in saved],'dds_registers':regs,'profiles':profiles},indent=2))
def key(ch,a):return (ch.device.id,ch.id,ch.output,a)
def remember(ch,a):
 if not any(key(x[0],x[1])==key(ch,a) for x in saved):saved.append((ch,a,ch.attrs[a].value))
def write(ch,a,v):
 remember(ch,a);persist_snapshot();ch.attrs[a].value=str(v)
# Snapshot shared DDS enables and all settings before any writes.
for ch in dds:
 for a in ['scale','frequency','phase','raw']:remember(ch,a)
for j in range(2):
 remember(p.find_channel('voltage'+str(j),True),'hardwaregain')
 ch=p.find_channel('voltage'+str(j),False)
 for a in ['gain_control_mode','hardwaregain']:remember(ch,a)
remember(p.find_channel('voltage0',False),'sampling_frequency')
remember(lo,'frequency');remember(tlo,'frequency');persist_snapshot()
def read_line():
 assert select.select([proc.stdout],[],[],10)[0], 'probe deadline'
 line=proc.stdout.readline()
 assert line, 'probe terminated: '+proc.stderr.read()
 return line.strip()
def stop_probe():
 global proc
 if proc:
  if proc.poll() is None:
   proc.stdin.write('q\n');proc.stdin.flush()
   print(read_line(),flush=True)
  assert proc.wait(timeout=10)==0,proc.stderr.read()
  proc=None
freqs=[959687500,1209687500,1459687500,1709687500]
fs=2500000;n=16384;tone=250000
oldlo=lo.attrs['frequency'].value
try:
 for ch in dds:write(ch,'scale',0)
 for j in range(2):write(p.find_channel('voltage'+str(j),True),'hardwaregain',-89.75)
 write(p.find_channel('voltage0',False),'sampling_frequency',fs)
 for j in range(2):
  ch=p.find_channel('voltage'+str(j),False);write(ch,'gain_control_mode','manual');write(ch,'hardwaregain',30)
 for ch in rx.channels:ch.enabled=True
 for j in range(4):
  tx.reg_write(0x414+j*0x40,regs[0x414+j*0x40]&~1);tx.reg_write(0x418+j*0x40,3 if j<2 else 0)
 for j,phase in [(4,0),(6,270000)]:
  write(dds[j],'frequency',tone);write(dds[j],'phase',phase);write(dds[j],'scale',0.1);write(dds[j],'raw',1)
 tx.reg_write(0x44,1)
 for target,frequency in enumerate(freqs):
  write(p.find_channel('voltage1',True),'hardwaregain',-89.75)
  write(tlo,'frequency',frequency)
  for j,f in enumerate(freqs):
   write(lo,'frequency',f);lo.attrs['fastlock_store'].value=str(j)
  write(lo,'frequency',oldlo)
  write(p.find_channel('voltage1',True),'hardwaregain',-40)
  proc=subprocess.Popen([ssh,'/tmp/issue119_recall 2500000'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
  assert read_line()=='READY'
  for repeat in range(3):
   for profile in [0,0,1,2,3,3]:
    proc.stdin.write(str(profile)+'\n');proc.stdin.flush();receipt=json.loads(read_line())
    assert abs(receipt['profile_frequency_hz']-freqs[profile])<=2 and receipt['crc']!=0
    assert 0<receipt['ticks']<fs//10
    buf=iio.Buffer(rx,n,False)
    try:
     buf.refill();data=np.frombuffer(buf.read(),dtype='<i2').reshape(-1,4).astype(float)
     # Baseline FPGA counter prefixes occur every 8192 dual-RX samples.
     # Analyze an interior 4096-sample IQ-only window away from both prefixes.
     data=data[1024:5120]
    finally:del buf
    results=[]
    for j in (0,2):
     x=data[:,j]+1j*data[:,j+1];power=abs(np.fft.fft(x*np.hanning(len(x))))**2
     bins=np.fft.fftfreq(len(x),1/fs);mask=abs(bins-tone)<1000
     signal=float(max(power[mask]));noise=float(np.median(power[(abs(bins-tone)>2000)&(abs(bins)>2000)]))
     results.append({'tone_over_noise_db':float(10*np.log10(signal/max(noise,1e-20))),'peak_hz':float(bins[int(np.argmax(power))])})
    row={'tone_profile':target,'repeat':repeat,**receipt,'rx':results};rows.append(row)
    with (out/'visits.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
  stop_probe()
  assert lo.attrs['frequency'].value==oldlo
 # Compare matching vs nonmatching tone-band energy separately for each RX.
 for target in range(4):
  for j in range(2):
   matched=[r['rx'][j]['tone_over_noise_db'] for r in rows if r['tone_profile']==target and r['profile']==target]
   other=[r['rx'][j]['tone_over_noise_db'] for r in rows if r['tone_profile']==target and r['profile']!=target]
   assert min(matched)>25,(target,j,matched)
   assert min(matched)-max(other)>15,(target,j,matched,other)
 print(json.dumps({'result':'PASS','recalls':len(rows),'ticks_min':min(r['ticks'] for r in rows),'ticks_max':max(r['ticks'] for r in rows),'tone_checks':8}),flush=True)
finally:
 try:stop_probe()
 except Exception as e:
  restoration_errors.append(str(e))
  if proc:proc.terminate();proc.wait(timeout=10)
 for ch in dds:
  try:ch.attrs['scale'].value='0'
  except Exception as e:restoration_errors.append(str(e))
 for j in range(2):
  try:p.find_channel('voltage'+str(j),True).attrs['hardwaregain'].value='-89.75'
  except Exception as e:restoration_errors.append(str(e))
 for ch,a,v in sorted(saved,key=lambda x: 0 if x[1]=='sampling_frequency' else 2 if x[1]=='gain_control_mode' else 1):
  if ch.device.id==tx.id and a in ('frequency','phase','scale'):continue
  try:ch.attrs[a].value=v.split()[0] if a=='hardwaregain' else v
  except Exception as e:restoration_errors.append(f'{ch.id} {a}: {e}')
 for a,v in regs.items():
  try:tx.reg_write(a,v)
  except Exception as e:restoration_errors.append(str(e))
 for v in profiles:
  try:lo.attrs['fastlock_load'].value=v
  except Exception as e:restoration_errors.append(str(e))
 for ch,a,v in saved:
  if a=='hardwaregain' and not ch.output and ch.attrs['gain_control_mode'].value!='manual':continue
  actual=ch.attrs[a].value
  if actual!=v:restoration_errors.append(f'{ch.id} {a}: {actual} != {v}')
 (out/'restoration.json').write_text(json.dumps({'errors':restoration_errors,'rx_lo':lo.attrs['frequency'].value},indent=2))
 assert not restoration_errors,restoration_errors
