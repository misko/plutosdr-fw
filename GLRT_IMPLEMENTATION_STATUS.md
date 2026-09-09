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
| Explicit numerical profile and enforceable detector gates | In progress | Component-owned host/qualification tests |
| Bounded vector staging, finite-close accounting and timing | In progress | HDL regression; versioned host/kernel closure support |
| Reproducible build/package and saved/synthetic verification | In progress | Owned environment, pinned source inputs |
| Ethernet deployment and recovery policy | In progress | Exact local USB-to-Ethernet identity and ownership inspection |
| Hardware calibration, IQ/event transport and recovery | Not run | Requires qualified candidate and identified radio |
| Independent same-IQ live GLRT comparison | Not run | Requires actual retained Ethernet capture |
| Five-rate deployment/verification completion | Not achieved | Per-rate evidence required; no aggregate success inferred |

Initial passive USB inventory found the excluded serial plus
`winbond-db6968136727402c` and `winbond-db620818a328172c`.
Neither eligible-looking serial is yet selected or assumed idle.
