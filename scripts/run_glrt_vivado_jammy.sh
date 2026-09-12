#!/usr/bin/env bash
# Invoke under sudo unshare --mount --propagation private. The build namespace
# exposes source/toolchains read-only and only the evidence tree as writable.
set -euo pipefail
test "$(id -u)" = 0
jammy_root=/srv/bulk/leo/glrt-deployment-20260909/vivado-jammy-v1/rootfs
evidence_root=/srv/bulk/leo/glrt-deployment-20260909
for target in /opt/Xilinx /home/mouse9911/gits "$evidence_root" /proc /dev; do
  mkdir -p "$jammy_root$target"
done
for target in /opt/Xilinx /home/mouse9911/gits; do
  mount --bind "$target" "$jammy_root$target"
  mount -o remount,bind,ro "$jammy_root$target"
done
mount --bind "$evidence_root" "$jammy_root$evidence_root"
mount -t proc proc "$jammy_root/proc"
mkdir -p "$jammy_root/dev/shm"
mount -t tmpfs -o size=1G,mode=1777 tmpfs "$jammy_root/dev/shm"
if [[ ! -e "$jammy_root/dev/fd" && ! -L "$jammy_root/dev/fd" ]]; then
  ln -s /proc/self/fd "$jammy_root/dev/fd"
fi
for device in null zero random urandom; do
  touch "$jammy_root/dev/$device"
  mount --bind "/dev/$device" "$jammy_root/dev/$device"
done
exec chroot "$jammy_root" /usr/sbin/runuser -u mouse9911 -- "$@"
