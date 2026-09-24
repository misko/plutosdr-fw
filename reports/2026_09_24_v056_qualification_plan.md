# v0.56 hardware qualification plan

This is a bounded, fail-closed qualification campaign for
`v0.56-plutoplus-spf-adaptive-runtime-rates`. It does not authorize flashing,
publishing, or any persistent device change.

## Preconditions and identity

1. Build the release through the v0.56 source route and retain its candidate
   JSON, DFU, and committed `adaptive-runtime-rates-v056-source.yaml`.
2. Use `scripts/release_v056/prepare.py` to create a new binding. It requires
   the exact v0.56 version, a full source commit, source-manifest SHA-256, and
   DFU SHA-256. Old v0.55 identities and hashes are not accepted.
3. Perform the separately controlled, serial-bound RAM test. Do not flash from
   this campaign. Only after a successful RAM receipt may a designated test
   radio be physically cold-cycled by removing and reconnecting all power.
4. Record a cold-cycle receipt with operator, serial, power-off/on UTC times,
   observed post-cycle firmware identity, and successful rediscovery. A
   software reboot is not a substitute.

## RX-only capture campaign

Supply a fresh inventory JSON using schema
`plutosdr-fw.v056-radio-inventory/v1`, mapping exactly the two allowlisted
serials to their currently attested `ip:` URIs. The plan hashes that inventory;
it does not embed or guess a LAN address.

Use one exact SHA-bound companion host tool: the PR126 / `b1097fb` compatible
`v056_adaptive_qualification.py`. It owns every cell and emits only
`org.leo.issue111.adaptive-capture/v1` reports. Every generated command carries
`--cell`, `--output`, `--ledger`, `--candidate`, `--inventory`, `--campaign-id`,
`--budget-seconds 11520`, `--serial`, `--uri`, `--rate-hz`, `--rx-mask`, and
`--duration-seconds`. Create the plan with `campaign.py plan`, inspect commands
with `campaign.py emit`, and only then opt in to `emit --execute`. The tools
contain no deploy, flash, power, or discovery-sweep action.

For each allowlisted local test radio, collect:

- 10 independent, 300-second, dual-RX (`rx-mask=3`) 2.5 MS/s counter-gap cells.
- One 300-second dual-RX adaptive cell at each new runtime rate: 5, 7.5, and 8 MS/s.
- One 300-second single-RX cell at each legacy rate: 10, 15, and 20 MS/s.

That is 32 cells and 9,600 seconds of reserved capture time. The fresh Issue
111 ledger must declare at least 11,520 seconds: 32 worst-case 360-second
reservations. The ledger must not exist before the first command. This is
fail-closed and no-retry: once a ledger exists, an interrupted or failed
campaign is retained; begin again only with a wholly new campaign ID, ledger,
and output root. The explicit
counter-gap campaign does not claim to reproduce the prior intermittent gap;
a clean result neither attributes nor excludes that incident.

## Acceptance

`campaign.py validate` passes only when every immutable report exists and
matches the one adaptive schema, exact serial, URI, rate, RX mask, candidate,
inventory, its own post-reservation ledger hash, and 300-second duration. A
single missing, malformed, mismatched, or failed cell is a failed campaign. It
additionally requires a physical-cold-cycle receipt proving all power was
removed and reconnected, RFC3339 power-on strictly after power-off, and
rediscovery of the exact image and source commit; a software reboot does not
satisfy this receipt.

UTC accuracy remains unresolved: counter/UTC anchors and timing-query success
are valuable timing evidence but do not qualify UTC accuracy without the
independent calibrated timing reference required by the Issue 107 contract.
