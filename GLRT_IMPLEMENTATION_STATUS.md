**GLRT implementation and Ethernet deployment — active, 9 September 2026**

User instruction: implement, test, deploy and verify. Use a locally USB-connected
radio other than `1040007c4a94000211000b009186843ef2`, and operate it over Ethernet.
This supersedes the review's proposed .18 target and historical target choices.
Exact device identity, current ownership and recoverability remain prerequisites
for hardware mutation. TX remains muted; RF collection windows are bounded to
at most 30 minutes, with short captures and saved-data analysis between them.

Persistent goal belongs to task `01a08439-8ad1-7b41-af10-f6329917f083`.
Implementation branch: `codex/glrt-deployment-implementation`, workspace
`/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review`.
Firmware baseline: `6e49144af`; review: `7dc653acd`.
HDL, Linux, Buildroot and U-Boot have independent working directories, each on
the implementation branch. The original GLRT workspace is a read-only reference.

The review's documentation-only statement describes the completed review, not
the current user-authorized implementation/deployment work. Hardware actions
will use the newly selected eligible radio, not the excluded serial.

| Work package | State | Evidence / next action |
|---|---|---|
| Explicit numerical profile and enforceable detector gates | Implemented | Frozen `glrt-upper-candidate-v1`; all complete strong frames required; failure exits nonzero |
| Bounded vector staging and finite-close accounting | Implemented and tested | Additive GLX1; HDL `ec87261d` paired-bin scorer halves service time; all five rates pass strict simulation |
| Kernel and strict host closure | Implemented and tested | Linux `93a343f29717` build passed; dedicated DT explicitly selects AD9361; completed event support must fit the attested native endpoint |
| Reproducible build/package and saved/synthetic verification | Numerical checks passed; physical closure partial | Fresh 50-case five-rate matrix: 45/45 strong frames; 15 quiet controls; 500,000 IQ words and 327 raw scores bit exact. HDL625a saved batch: 24 recordings, 1.2M IQ words, 116 vectors exact |
| Routed implementation | 2.5, 5, 10 MS/s pass; 25 and 60 fail | Setup slacks +0.009, +0.013, +0.055, -0.341, -0.938 ns respectively. Failed high-rate images are not deployable; measured control-path fix in progress |
| Ethernet deployment and recovery policy | Implemented and used | Exact source FIT, serial, USB recovery presence, idle buffers and ownership lock required; original persistent backup retained |
| Hardware calibration, IQ/event transport and recovery | First candidate deployed; commissioning active | 2.5 MS/s RX PN eye passed at delay0x08, 140 passing points. First 300,000 samples received; final snapshot race caused explicit failed capture, fixed with bounded current-visit wait and 58 tests |
| Independent same-IQ live GLRT comparison | Pending successful capture | Receiver feed/IF remains unknown; transport evidence cannot establish live pilot sensitivity |
| Five-rate deployment/verification completion | Not achieved | Per-rate evidence required; no aggregate success inferred |

Selected receiver: `192.168.1.14`, serial `winbond-db620818a328172c`, physically
present at USB `5-1`. Read-only inspection found a 1000 Mb/s full-duplex Ethernet
link, idle IIO buffers and no held shared radio lock. Recheck at each mutation.
The excluded serial was not operated.

The pre-deployment active runtime was `v0.48-plutoplus-spf-iq-direct-async-v3`; the independently
downloaded and extracted persistent QSPI FIT is v0.47 direct-async-v2. These are
different baselines. Exact persistent FIT: 12,826,107 bytes, SHA256
`7a198f961cd6765ebd831c21314baac0f962650541af671911c23e76db33cbc2`.
Rollback must expect that verified v0.47 image, not claim to restore the active
v0.48 RAM bytes. A verified published v0.48 artifact is separately retained.
Original U-Boot environment remains preserved; its mode handling does not add
2R2T to the candidate's compiled 1R1T device tree.

Build and numerical evidence is retained under
`/srv/bulk/leo/glrt-deployment-20260909`. Private recovery/enrollment material is
under the owned device tool's ignored `artifacts/ethernet-canary-14` directory.
The first persistent candidate `glrt-eth-r2500000-v1` was written and its exact
QSPI FIT verified over Ethernet. It rebooted successfully. The initial deployment
receipt remains `unknown` because its return validator looked for a device-level
sampling attribute on a channel. A separate read-only reconciliation receipt
verifies the running candidate, new boot identity, exact FIT, GLR1/GLX1, idle
buffers, muted TX and gigabit link without rewriting the original receipt.
The candidate FIT SHA256 is
`e447ccc721927f69abe38f46bf6d9694f1d9a83b1f242a040b84500aa27e30b0`.

The old U-Boot AD9361 override uses `/amba`, but this kernel's PHY is under `/axi`.
The deployed v1 therefore reports AD9363a. The dedicated DT fix is compiled and
packaged as `glrt-eth-r2500000-v2`, FIT SHA256
`df5eece95500896aebf7980a24af1ad129d46633690a8e75b9afb3fe19e69fab`.
It preserves Rev.C identity, 1R1T topology and the existing U-Boot environment.
The original persistent rollback and subsequent GLRT redeployment remain to be
exercised. No image is declared production or live-detector qualified.

First RX-only transport collection used the observed post-boot 2.4 GHz LO,
2 MHz bandwidth, RX A_BALANCED and manual 30 dB gain. These settings are for
transport commissioning and do not identify the connected RF feed.
Live pilot verification still depends on the selected receiver's actual RF feed;
transport and closure tests do not establish Starlink sensitivity.
