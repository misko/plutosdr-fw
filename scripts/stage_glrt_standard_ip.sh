#!/usr/bin/env bash
# Reuse only standard ADI IP metadata with identical declared source bytes.
# The changed GLRT IP and complete board implementation are always rebuilt.
set -euo pipefail
[[ $# -eq 2 ]]
target=$(realpath "$1")
cache=$(realpath "$2")
test -d "$target/.git"
(cd "$target" && sha256sum --check --status "$cache/source.sha256")
(cd "$cache/hdl" && sha256sum --check --status "$cache/metadata.sha256")
while read -r checksum name; do
  case "$name" in
    library/axi_ad9361/*|library/axi_dmac/*|library/util_cdc/*|library/util_axis_fifo/*) ;;
    *) echo 'cache entry outside standard IP' >&2; exit 2 ;;
  esac
  [[ "$name" != *..* && "$checksum" =~ ^[0-9a-f]{64}$ ]]
  test ! -e "$target/$name"
done < "$cache/metadata.sha256"
while read -r checksum name; do
  mkdir -p "$(dirname "$target/$name")"
  cp "$cache/hdl/$name" "$target/$name"
done < "$cache/metadata.sha256"
(cd "$target" && sha256sum --check --status "$cache/metadata.sha256")
for core in util_cdc util_axis_fifo axi_ad9361 axi_dmac; do
  make -q -C "$target/library/$core" component.xml
done
cp "$cache/source.sha256" "$target/../standard-ip-source.sha256"
cp "$cache/metadata.sha256" "$target/../standard-ip-metadata.sha256"
sha256sum "$0" > "$target/../standard-ip-stage-script.sha256"
