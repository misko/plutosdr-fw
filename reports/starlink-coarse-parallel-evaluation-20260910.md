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
