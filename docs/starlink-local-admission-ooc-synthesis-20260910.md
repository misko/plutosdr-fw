# L1/R1B1O1/175 OOC synthesis — resource result only

The single authorized synthesis completed: original57050 exit0,
12:29:08.979369–12:30:51.566419UTC,102.587s. Before audit, tool exit and after audit
are all0. Exactly one completion marker, eight nonempty products, zero black boxes.
No retry, RTL/constraint change or route was performed.

Source FW `38dfe9d80c33d841d75ebc2ffb46de09eb03b37b` /
HDL `67a1692e3b09f3aa7166fb8f83b1cf787b363f78`; tested runtime cohort62da6a39… .
Prepared inventory `4ebd909dad1ade64272a33dcc034b9f791270ce1191827266c83ad23ee86703b`.
Owner `hdl/library/starlink_pss_acquisition/build/local-admission-ooc-L1R1B1O1-175-owned-v1`.
Exact command/start/end/errors/product hashes are in its invocation/terminal JSON.

| Synthesized resource | Arithmetic baseline | L1 | Change |
| --- | ---: | ---: | ---: |
| LUT | 1,944 | 1,945 | +1 |
| Logic LUT / SRL LUT | 1,756 /188 | 1,757 /188 | +1 /0 |
| Flip-flop | 4,547 | 4,547 | 0 |
| DSP48E1 | 21 | 21 | 0 |
| RAMB18 / BRAM tiles | 15 /7.5 | 15 /7.5 | 0 |

The input guard is59 LUT/85 FF; the other major hierarchy counts are unchanged:
FFT1,205 LUT/2,989 FF/17 DSP/11 RAMB18, product60 LUT/357 FF/4 DSP,
result guard137 LUT/180 FF. These are synthesized hierarchy counts, not a routed
area saving or receiver-fit claim. The full hierarchy report is retained.

Effective synthesis generics explicitly include REGISTERED_SCHEDULING=1,
BOUNDARY_ROUND_SAT=1, REGISTER_OPERANDS=1 and LOCAL_FIRST_ADMISSION=1; RTL default L
remains0. PRIVATE_PAYLOAD_BUBBLES remains1. Vivado2022.2/xc7z010clg400-1,
AreaOptimized_high/OOC/control threshold4 and two threads remain unchanged.

Clock report: source100 period10ns, island175 period5.714000225ns (reported tool
quantization), identical clock recipe. Check-timing still reports114 missing input
delays and124 missing output delays;0 unconstrained internal endpoints/no-clock
pins/loops. CDC reports6 Info and139 Warning entries. These checks do not establish
timing closure, CDC safety or external-interface timing.

All12 copied inputs plus adapted Tcl pass pre/post identity checks. The generated
FFT VHDL is rehashed after synthesis against its before-synthesis scope receipt:
`a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`.
The actual numerical evidence source is unchanged and remains independently gated.

Final synthesis DCP SHA:
`a6a8e404b90924bb538a0da2ae7be7fc9ebc9e0c323b8f1a17661b4550648242`.
The original arithmetic baseline DCP is de5b7ca6…; its diagnostic route still has
175MHz WNS−1.341ns. No L1 routed slack is available from synthesis, and no new
clock or timing-pass claim follows. The unchanged route0873675f… requires separate
source-specific authority. No D/S/CDC union, receiver/radio work or promotion.
