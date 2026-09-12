#!/usr/bin/env bash
# Rebuild the candidate from immutable local sources and the verified release DFU.
set -euo pipefail
task_root=$(cd "$(dirname "$0")/../.." && pwd)
: "${PLUTO_TOOLCHAIN_ROOT:?Set the Linaro Buildroot host-toolchain directory}"
: "${BASELINE_DFU:?Set the exact v0.49 DFU path}"
counter_linux=${COUNTER_LINUX_SOURCE:-"$task_root/../plutosdr-linux-issue-97"}
counter_libiio=${COUNTER_LIBIIO_SOURCE:-"$task_root/../libiio-issue-97"}
test "$(git -C "$counter_linux" rev-parse HEAD)" = 4683cd2e3556448295e03a216a3a7fc6e8bbc474
test "$(git -C "$counter_libiio" rev-parse HEAD)" = 47a75cbc5e7d24a063b8b54eb531fdba6602b85c
test -z "$(git -C "$counter_linux" status --porcelain)"
test -z "$(git -C "$counter_libiio" status --porcelain)"
mkdir -p "$task_root/build/metadata-source/linux"
export ISSUE97_ROOT="$task_root"
python3 - <<'PY'
import os, hashlib
from pathlib import Path
data=Path(os.environ['BASELINE_DFU']).read_bytes()
assert hashlib.sha256(data).hexdigest()=='f45524f4765d5743144703ff6f4541084ff1ab9b1ce20a77f3f6fa820a1f84b6'
Path(os.environ['ISSUE97_ROOT'],'build/baseline.itb').write_bytes(data[:-16])
PY
git -C "$task_root" archive 3294365ff44da26b261be4a2ccb241b7896d23ad | tar -x -C "$task_root/build/metadata-source"
cp "$counter_linux/include/uapi/linux/adi_tandem_agc.h" "$task_root/build/metadata-source/linux/"
images=(zynq-pluto-sdr.dtb zynq-pluto-sdr-revb.dtb zynq-pluto-sdr-revc.dtb system_top.bit baseline-zImage baseline-rootfs.cpio.gz)
for index in "${!images[@]}"; do
    dumpimage -T flat_dt -p "$index" -o "$task_root/build/${images[$index]}" "$task_root/build/baseline.itb"
done
cross="$PLUTO_TOOLCHAIN_ROOT/bin/arm-linux-gnueabihf-"
make -C "$counter_linux" O="$task_root/build/linux" ARCH=arm CROSS_COMPILE="$cross" LOCALVERSION= zynq_pluto_defconfig
"$counter_linux/scripts/config" --file "$task_root/build/linux/.config" --set-str LOCALVERSION -counter-rx-v1 --disable LOCALVERSION_AUTO
make -C "$counter_linux" O="$task_root/build/linux" ARCH=arm CROSS_COMPILE="$cross" LOCALVERSION= olddefconfig
make -C "$counter_linux" O="$task_root/build/linux" ARCH=arm CROSS_COMPILE="$cross" LOCALVERSION= -j"${JOBS:-8}" zImage modules
make -C "$counter_linux" O="$task_root/build/linux" ARCH=arm CROSS_COMPILE="$cross" LOCALVERSION= INSTALL_MOD_PATH="$task_root/build/modules" modules_install
# Supply the unpublished source archive to an optional Buildroot download cache.
export COUNTER_ARCHIVE_SOURCE="$counter_libiio"
python3 - <<'PYARCHIVE'
import os, subprocess, gzip, hashlib
from pathlib import Path
pin='47a75cbc5e7d24a063b8b54eb531fdba6602b85c'
archive=subprocess.check_output(['git','-C',os.environ['COUNTER_ARCHIVE_SOURCE'],'archive','--format=tar','--prefix=libiio-'+pin+'/',pin])
data=bytearray(gzip.compress(archive,mtime=0))
data[9]=3  # Match the reviewed Linux gzip OS byte across Python versions.
data=bytes(data)
assert hashlib.sha256(data).hexdigest()=='ea57455d7c1e4b66f02e50cf1de7be09421f28f1c281803958c836a208922867'
Path(os.environ['ISSUE97_ROOT'],'build','libiio-'+pin+'.tar.gz').write_bytes(data)
if os.environ.get('COUNTER_BUILDROOT_DL'):
    path=Path(os.environ['COUNTER_BUILDROOT_DL'])/'libiio'/('libiio-'+pin+'.tar.gz')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
PYARCHIVE
metadata="$task_root/build/metadata-source"
extras="$counter_libiio/iiod/spf-tandem-session.c;$counter_libiio/iiod/spf-tandem-metadata.c"
for source in spf_gain_read spf_gain_sampler spf_rssi_read spf_radio_frame_v3 spf_thread_join; do
    extras="$extras;$metadata/$source.c"
done
cmake -S "$counter_libiio" -B "$task_root/build/libiio-arm" \
    -DCMAKE_TOOLCHAIN_FILE="$task_root/scripts/issue97/arm-toolchain.cmake" \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo -DWITH_TESTS=OFF -DWITH_USB_BACKEND=OFF \
    -DWITH_SERIAL_BACKEND=OFF -DWITH_DOC=OFF -DWITH_IIOD=ON -DWITH_AIO=ON -DHAVE_DNS_SD=OFF \
    -DIIOD_BUFFER_METADATA_PROVIDER="$counter_libiio/iiod/spf-buffer-metadata.c" \
    -DIIOD_BUFFER_METADATA_PROVIDER_EXTRA_SOURCES="$extras" \
    -DIIOD_BUFFER_METADATA_INCLUDE_DIRS="$metadata"
cmake --build "$task_root/build/libiio-arm" --parallel "${JOBS:-8}"
python3 "$task_root/scripts/issue97/package.py"
