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
| Bounded vector staging and finite-close accounting | Implemented, physical build running | HDL `b4834272`; 9/9 strong 2.5 MS/s frames recovered; GLX1 is additive to unchanged GLR1 |
| Kernel and strict host closure | Implemented and tested | Linux `36c6561f152a`; fresh kernel build passed; completed event support must fit the attested native endpoint |
| Reproducible build/package and saved/synthetic verification | In progress | Firmware `6493efd96`; pinned host oracle `5f25fc57`; 2.5 MS/s full board build running |
| Ethernet deployment and recovery policy | Implemented and tested | Device tool `d75c5c2`; exact source FIT, serial, USB recovery presence, idle buffers and ownership lock required |
| Hardware calibration, IQ/event transport and recovery | Not run | Requires qualified candidate and identified radio |
| Independent same-IQ live GLRT comparison | Not run | Requires actual retained Ethernet capture |
| Five-rate deployment/verification completion | Not achieved | Per-rate evidence required; no aggregate success inferred |

Selected receiver: `192.168.1.14`, serial `winbond-db620818a328172c`, physically
present at USB `5-1`. Read-only inspection found a 1000 Mb/s full-duplex Ethernet
link, idle IIO buffers and no held shared radio lock. Recheck at each mutation.
The excluded serial was not operated.

The active runtime is `v0.48-plutoplus-spf-iq-direct-async-v3`; the independently
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
No hardware mutation or new RF collection has occurred at this checkpoint.
Live pilot verification still depends on the selected receiver's actual RF feed;
transport and closure tests do not establish Starlink sensitivity.
