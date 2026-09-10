# Parallel coarse-engine evaluation — experimental only

The user explicitly requested an independent subagent and worktree for every
alternate approach. Three agents were launched on 2026-09-10 UTC. The primary
agent continues the existing idle-admission timing experiment separately.

All alternatives start from the same committed firmware `ec36b96965df76f83b80e70c1aba867e7cbbbc30`
and HDL `eb96c64738697c10b9c0abb379ab64f6a4a5c59c`, not the primary worktree's
uncommitted files or newly promoted candidate. Each has independent firmware
and nested HDL Git worktrees; only Git object storage is shared.

| Agent | Firmware worktree (HDL is its `hdl/`) | Branch in both repositories |
| --- | --- | --- |
| `coarse_fft_island` | `/tmp/starlink-coarse-alternatives.Y3JzOI/fft-island` | `codex/starlink-rx-only-do-not-merge-fft-island` |
| `coarse_direct_correlator` | `/tmp/starlink-coarse-alternatives.Y3JzOI/direct-coarse` | `codex/starlink-rx-only-do-not-merge-direct-coarse` |
| `coarse_narrow_acquisition` | `/tmp/starlink-coarse-alternatives.Y3JzOI/narrow-coarse` | `codex/starlink-rx-only-do-not-merge-narrow-coarse` |

## Bounded deliverables

- Consolidated island: actual-core first slice or executable cycle/dataflow
  model keeping FFT, template multiply and inverse processing local. Charge
  outer clock-crossing/bank costs and retained ACK/reset/config overhead.
- Direct correlator: coefficient provenance and independently evaluated
  numerical/cycle prototype, with resource measurement where practical. The
  original Q15 taps and quantized frequency-domain/BFP chain are distinct
  numerical contracts; unchanged goldens remain the reference.
- Narrow acquisition: offline sensitivity/CFO/filter-support and causal
  assistance study. No assumed host real-time capacity, post-hoc seed leakage,
  or hidden filtered-out negatives. Original-rate fine search remains required.

Each agent must report executed tests, source/artifact identities, measured
limits and open integration work. A negative result is useful. No architecture
is selected from an unexecuted proposal or isolated area estimate.

## Ownership and promotion boundaries

No agent may access radios, edit PPU or another worktree, merge into main, push
remotes, launch a full receiver build, waive timing constraints, or remove a
detector. Qualified local branch commits are permitted for review. There are
no delegated radio ownership locks. The primary full build retains coarse and
fine PSS, pilot DMA and the original clocks/constraints. Alternative full-build
selection follows review so source identities remain unambiguous.

The full objective is unchanged: original-rate fine search at 15/30/60 MS/s,
independent 2.5 MS/s pilot IIO capture, .18 then Ethernet/PPU .17 verification,
eight lower/upper targets with 120 ms valid dwells over 300 s, and independent
live GLRT/PSS agreement. Neither simulation nor 16.7 ns sample spacing is a
deployment or accuracy claim.

## Completed first studies and independent review

All three agents finished on 2026-09-10 UTC. The root read each complete report,
checked clean firmware/HDL worktrees and exact commit identities, and reran the
20 newly added unit tests: island8, direct3, narrow9, all passing. These are
independent unit-test reruns, not repeated physical builds or the complete
offline data experiments. Agent-run evidence and its limits remain separate.

| Alternative | Firmware commit | HDL commit |
| --- | --- | --- |
| FFT island | `d88ad998d4207972855b92ee92fdf9e3a099f3dc` | `456f6d76aa82751f4db50323c648a885ee49c47a` |
| Direct coarse | `84c48b347cc0c7f13f15403eaa174f9076d4fda3` | `a29d4fc27e2b92311131d07c53fb559bff37c697` |
| Narrow assistance | `3f192ada5ae79b7e7f4afe96f129f2b20cc84d0b` | `eb96c64738697c10b9c0abb379ab64f6a4a5c59c` (unchanged) |

These alternative branches are local; no remote push or merge was performed
by the agents. Their committed reports are respectively:
`docs/starlink-fft-island-slice-20260910.md`,
`docs/starlink-direct-coarse-evaluation-20260910.md`, and
`reports/starlink-narrow-coarse-feasibility-20260910.md`, in the worktrees above.

| Approach | Executed evidence | Current limiting result |
| --- | --- | --- |
| Consolidated FFT island | Actual generated core:23 healthy blocks,11776 exact inverse words, reset/flush and fault cases | 5182-clock nominal interval at200MHz leaves3.89us/block; a measured6130-clock stalled profile exceeds29.8us. Outer CDC banks remain modeled, not implemented; no physical result. |
| Direct66-tap coarse |119 RTL arithmetic/protocol jobs;102 numerical controls; actual isolated route |2/102 controls fail unchanged FFT comparison, up to9 score LSBs.2087LUT/2442FF/18DSP slice passes setup(+.453ns), fails hold(-.713ns); history/normalization/CDC are extra. |
| Narrow pilot/GLRT assistance |12 synthetic and9 real20ms probes;69 focused tests | Supported fixtures pass, but real CFO aliases remain. Measured x86 search28.13–62.16ms is not target CPU capacity; future-frame handoff49.48–83.51ms excludes transport/control/fine cost. |

The direct result defines a different arithmetic contract; matching an independent
float oracle on its failing dynamic-range controls does not establish better
detection or authorize changing production acceptance tolerances. Narrow
assistance is a candidate aid, not a replacement for native fine evidence.

The root's unchanged-clock full idle-admission receiver build also completed
with exit1 at00:20:46UTC. WNS -1.269ns and355 failing endpoints regress from
the retained best18c reference. No build artifact is deployment eligible.
The worst path has6.100ns data delay, including4.900ns routing, between input
cursor and result input-count control. This and full slice occupancy support
investigating locality and complete resource budgets; they do not prove which
alternative will close timing.

## Next bounded comparison, not a selected replacement

1. Prioritize a second FFT-island experiment that removes redundant local bank
   copies through validated ownership handoff. Preserve exact arithmetic,
   current faults, late-fault quarantine, reset/ACK and complete publication.
   At150MHz the measured first slice needs at least713 clocks removed merely
   to get positive nominal margin; removing one512-clock copy is insufficient.
2. Measure the complete island including outer banks, both edges, original
   energy/normalization and sustained stalls, then its actual resource/physical
   cost before commissioning another full receiver build.
3. Keep direct as a separately scored fallback until numerical acceptance,
   complete history/normalization cost and real hold closure are demonstrated.
   Do not spend a full receiver route on the current incomplete arithmetic slice.
4. Keep narrow pilot evidence independent and study alias-preserving future-frame
   commands. Charge real host/transport/control/compute deadlines and expire
   stale visit-tagged predictions; do not assume a retrospective native60 ring.

The measured reference-resource inventory and reproducible read-only reports are
in `reports/experiments/20260910-coarse-reference-resources.md` and its archive.
Normalization and20BRAM tiles of coarse maps remain material costs regardless
of the FFT choice. No source-rate fine search or pilot output is removed.
