#!/usr/bin/env python3
"""Build a private kernel and iiOD candidate from the qualified v0.59 DFU."""
import argparse,gzip,hashlib,json,struct,subprocess,zlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--kernel',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--iiod',type=Path,required=True);p.add_argument('--libiio',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=True)
raw=a.base.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='1fa69d2784efbcabaaaed5bc5f5d625deabfd7da725627c9634a694db5bd9df0'
(a.out/'baseline.itb').write_bytes(raw[:-16])
names=['zynq-pluto-sdr.dtb','zynq-pluto-sdr-revb.dtb','zynq-pluto-sdr-revc.dtb','system_top.bit','baseline-zImage','rootfs.cpio.gz']
for i,name in enumerate(names):
 subprocess.run(['dumpimage','-T','flat_dt','-p',str(i),'-o',str(a.out/name),str(a.out/'baseline.itb')],check=True,stdout=subprocess.DEVNULL)
# Preserve every archive entry and ownership; replace the reviewed binaries and release identity.
data=gzip.decompress((a.out/'rootfs.cpio.gz').read_bytes());out=bytearray();pos=0;versions=None;replaced=set()
while pos<len(data):
 start=pos;header=data[pos:pos+110];assert header[:6]==b'070701';fields=[int(header[6+i*8:14+i*8],16) for i in range(13)]
 size,namesize=fields[6],fields[11];name=data[pos+110:pos+110+namesize];pos=(pos+110+namesize+3)&~3;body=data[pos:pos+size];pos=(pos+size+3)&~3
 if name.rstrip(b'\0') in (b'opt/VERSIONS',b'./opt/VERSIONS'):
  versions=body.decode();body=body.replace(b'device-fw v0.59-plutoplus-spf-dual-rx-counter-fix',b'device-fw v0.59-issue119-fastlock-rc2')
  body=body.replace(b'linux adaptive-multirate-agc-v059-source/linux-v2',b'linux fastlock-attestation-v059-source/linux-v1')
  body=body.replace(b'buildroot adaptive-multirate-agc-v058-source/buildroot-v2',b'buildroot fastlock-attestation-v059-source/buildroot-v1')
  fields[6]=len(body)
 replacements={b'usr/sbin/iiod':a.iiod,b'usr/lib/libiio.so.0.25':a.libiio}
 key=name.rstrip(b'\0').removeprefix(b'./')
 if key in replacements:
  body=replacements[key].read_bytes();fields[6]=len(body);replaced.add(key)
 out+=b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)+name
 out+=b'\0'*((-len(out))%4);out+=body;out+=b'\0'*((-len(out))%4)
 if name.rstrip(b'\0')==b'TRAILER!!!':break
assert replaced=={b'usr/sbin/iiod',b'usr/lib/libiio.so.0.25'}
assert versions and b'device-fw v0.59-issue119-fastlock-rc2' in out
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
manifest={'base_sha256':hashlib.sha256(raw).hexdigest(),'firmware':'v0.59-issue119-fastlock-rc2','scope':'Fast Lock selection/lock/counter hardening and iiOD final-dwell deadline handling; profile frequency remains derived from SRAM','sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in a.out.iterdir() if f.is_file() and f.name!='manifest.json'}}
(a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'fit_size':len(fit),'sha256':manifest['sha256']['pluto.dfu']}))
