#!/usr/bin/env python3
"""Build a private kernel-only candidate from the qualified v0.54 DFU."""
import argparse,gzip,hashlib,json,struct,subprocess,zlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--kernel',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=True)
raw=a.base.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='3611adb9d38d5db9e6e94453a195194022dd7c7ba0ca649234f783d1bb016ada'
(a.out/'baseline.itb').write_bytes(raw[:-16])
names=['zynq-pluto-sdr.dtb','zynq-pluto-sdr-revb.dtb','zynq-pluto-sdr-revc.dtb','system_top.bit','baseline-zImage','rootfs.cpio.gz']
for i,name in enumerate(names):
 subprocess.run(['dumpimage','-T','flat_dt','-p',str(i),'-o',str(a.out/name),str(a.out/'baseline.itb')],check=True,stdout=subprocess.DEVNULL)
# Preserve every archive entry and ownership; replace only the release identity.
data=gzip.decompress((a.out/'rootfs.cpio.gz').read_bytes());out=bytearray();pos=0;versions=None
while pos<len(data):
 start=pos;header=data[pos:pos+110];assert header[:6]==b'070701';fields=[int(header[6+i*8:14+i*8],16) for i in range(13)]
 size,namesize=fields[6],fields[11];name=data[pos+110:pos+110+namesize];pos=(pos+110+namesize+3)&~3;body=data[pos:pos+size];pos=(pos+size+3)&~3
 if name.rstrip(b'\0') in (b'opt/VERSIONS',b'./opt/VERSIONS'):
  versions=body.decode();body=body.replace(b'device-fw v0.54-plutoplus-spf-counter-utc-v1-rc1',b'device-fw v0.54-issue119-fastlock-rc1')
  body=body.replace(b'linux adaptive-scan-v2-source/linux-v1',b'linux codex/issue-119')
  fields[6]=len(body)
 out+=b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)+name
 out+=b'\0'*((-len(out))%4);out+=body;out+=b'\0'*((-len(out))%4)
 if name.rstrip(b'\0')==b'TRAILER!!!':break
assert versions and b'device-fw v0.54-issue119-fastlock-rc1' in out
out+=b'\0'*((-len(out))%512)
(a.out/'rootfs.cpio.gz').write_bytes(gzip.compress(out,mtime=0))
(a.out/'zImage').write_bytes(a.kernel.read_bytes())
source=Path(__file__).resolve().parents[1]/'pluto.its'
its=source.read_text().replace('../build/','')
(a.out/'pluto.its').write_text(its)
subprocess.run(['mkimage','-f','pluto.its','pluto.itb'],cwd=a.out,check=True,stdout=subprocess.DEVNULL)
fit=(a.out/'pluto.itb').read_bytes()
suffix=struct.pack('<HHHH3sB',0xffff,0xb673,0x0456,0x0100,b'UFD',16)
body=fit+suffix;body+=struct.pack('<I',zlib.crc32(body)^0xffffffff)
(a.out/'pluto.dfu').write_bytes(body)
(a.out/'pluto.frm').write_bytes(fit+hashlib.md5(fit).hexdigest().encode()+b'\n')
manifest={'base_sha256':hashlib.sha256(raw).hexdigest(),'firmware':'v0.54-issue119-fastlock-rc1','scope':'kernel-only Fast Lock selection/lock/counter hardening; profile frequency remains derived from SRAM','sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in a.out.iterdir() if f.is_file() and f.name!='manifest.json'}}
(a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'fit_size':len(fit),'sha256':manifest['sha256']['pluto.dfu']}))
