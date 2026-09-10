# Bounded profile-transition correction and independent complete reassessment

The offline correction independently passes **111 tests**. Complete saved-run
reassessment also repeats successfully with an identical result hash. Original
actual21014 **remains automation FAIL**, with no successful results.json, no
modified recording and no vendor retry. See the
[first-result diagnosis](20260910-inverse-actual-first-result.md).

## Source and test boundary

Reviewed FW `fb186470204f314681a37c7fe2962d024e876e04`, HDL unchanged
`b26f56dd32106c8e91290d075255ac4a6b9ff72d` in the separate bank-arithmetic
DO-NOT-MERGE tree. Parent read the complete parser diff and new136-line test
file. Only trace parsing and its completed-epoch predicate change; all other
timing/protocol functions and constants are AST-identical to the frozen source.

A changed profile is allowed only after the exact64/12 healthy jobs and their
complete phases, in drained WAIT_BANK with core reset held, source/product
empty, output reusable, old final identity retained, and no current events or
faults. The only legal new profile is the next one. At most two175-MHz rows may
precede an adjacent same-epoch common-reset row, which is also checked. No old
epoch may resume traffic afterward. This models the unchanged bench's profile
assignment before its next-slow-negedge reset; it does not mask arbitrary idle
faults, unknown values, missing work or in-flight profile changes.

Parent original64617 exited0: **111 passed in63.83 seconds** (the old65 plus
new46), with these three source hashes identical before/after:

- Parser: `09061c6d56fab3460536cca74733f2da764ea6f2a2e508a11d4f4d60482f17c6`.
- Transition tests: `c98254326e14e22ff032d382061354d2248111806a54e2fa4db893af750c3df2`.
- Original policy tests: `05bcd90c6212682cc1a6c6fa7934ef891028d5db690b7cdeab77254572eadccc`.

The tests preserve/reproduce the original failure; exercise one/two-row healthy
transitions; reject26 active/ownership/fault/unknown variants and16 incomplete,
unbounded or broken-reset variants; and check the entire saved76-job timing,
all mixed-domain event timestamps and38 protocol lifetimes. These are offline
parser tests, not another execution of the FPGA core.

## Independent complete reassessment

Parent fully read `assess_original_21014.py`, SHA
`1662cd7c56e879e80c58f375d77df3b9874a8b1e5af171d288f1a76ad670ac91`.
It uses the exact frozen result collector code object with only the explicitly
audited timing-module binding replaced. AST comparison proves all other clock/
protocol code and constants unchanged. Exact failed outcome/owner/source pins,
all original numerical/guard/terminal/diagnostic checks and generated wrapper
identity remain required. It does not rewrite the original module's globals.

Parent copied that script and corrected timing file byte-identically to a new
recovery directory, verified their hashes and executed original79053 to exit0.
All211 original files match the archived inventory before and after; original
results.json is still absent. The reassessment SHA exactly matches the owner's:
`97eccd325d9c70411b692d0cc0103b09e100491dd66e6f6589126b8d3f824169`.
It explicitly records original_automation=FAIL and no new simulation. The
unconditional155-bit guard receipt includes1,180,858 pre/1,180,857 post checks,
17 current faults and897 sticky faults; these observations are not a substitute
for physical or full-receiver qualification. WDB recorded-history review remains
pending; diagnostic object inventory alone does not prove that history.

## Preserved parent artifacts and next gate

- `20260910-inverse-transition-parent.tgz`:28,449,820 bytes, SHA
  `86e13d309b98bedf80a3b8b2867215487ed1e728c2ddf6c512b980d8c841b75d`.
  Complete `inverse-transition-parent.R3esgpvT` test artifacts; log SHA
  `b470e4021d21f4a400da1695c85346b497d7365cc0755009bd6e0ab19333618e`,
  JUnit SHA `c110b5f9dfcebd28c34f8bc5910e77854e2d164f4fcdde5969773e78ba181eee`.
- `20260910-inverse-assessment-parent.tgz`:30,212 bytes, SHA
  `787c1359a4c10a0ade21347f1ed287bc6dd93de2d5154a9e6b1d68007151ff39`.
  Complete `inverse-assessment-parent.PHXKSIlS`, including exact copied scripts,
  reassessment and211-file before/after audit.

Both tar comparisons against original recovery directories exited0.
The next authorized work is preparation only: exclusive v2 bundle/owner with
exactly the corrected timing helper and resulting manifest different from v1.
No runtime, bench, clock or budget change is needed. A new actual launch needs
separate source-specific review and approval; none is authorized here. The
staged product and retained-consumer overlap alternatives remain separate.
Production gitlinks, radio/PPU state and all deployment gates are unchanged.
