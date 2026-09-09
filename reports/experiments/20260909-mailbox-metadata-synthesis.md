# Private mailbox metadata comparison — retained synthesis evidence

Experimental branch only: `codex/starlink-rx-only-do-not-merge`.
The candidate RTL is HDL `65adf692da07422f10fea6c342b2711807ff7a89`;
the baseline is `18c96bb93f0aea5f868fb8b4c15a2eb1bce7a873`.

`20260909-mailbox-metadata-synthesis.tgz` retains both actual Vivado 2022.2
functional netlists, both frozen mailbox sources, the measurement script,
source/netlist hashes, and isolated utilization/timing reports. Archive SHA256:
`c851aaed164907e1364271ecc9b3ee5f28677550424505b8514024ccb464f25e`.
It intentionally excludes DCPs and receiver bitstreams. This is not a firmware
package and must not be flashed.

From the firmware repository, with the matching HDL and Python test environment:

```bash
replay_dir=$(mktemp -d /tmp/starlink-metadata-replay.XXXXXX)
tar -xzf reports/experiments/20260909-mailbox-metadata-synthesis.tgz -C "$replay_dir"
STARLINK_PSS_METADATA_TREE_NETLIST_DIR="$replay_dir" \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -m pytest -q \
  tests/starlink_oracle/test_mailbox_metadata_tree.py
```

The replay requires local Vivado 2022.2, Icarus Verilog and both Git source
revisions. Original absolute paths in `scope.txt` are retained as provenance;
the verifier checks frozen content hashes and current source bytes, so replay
does not require the original temporary directory.

Both actual synthesized 512-word mailboxes are compared with frozen baseline
RTL, without depositing netlist state. Each must reject all 225 single-bit
metadata faults (75 bits at three noninitial slots, including the final edge)
and deliver 1536 healthy words with matching public outputs, stalls and ACK
reuse. The standalone combinational equality test separately and explicitly
forces only its held operand; that is not a native mailbox protocol claim.

The candidate maps to 84 LUT/187 FF/one RAMB18, versus 76 LUT/187 FF/one RAMB18.
Its framing cone contains one CARRY4 rather than eight. However, its *unrouted*
held-metadata path estimate is worse: 5.426 ns versus 5.202 ns. Shallower logic
alone does not establish faster receiver timing. The fresh complete routed
receiver, and later board-I/O/CDC/reset and native radio checks, remain the
required deployment gates. See `../starlink-mailbox-metadata-tree-20260909.json`.
