# GLI1 1.0: ARM acquisition and native scheduled tracking

GLI1 is a new receive-only board profile at exactly 30,000,000 or 60,000,000
complex samples per second. It exports continuous 2,500,000-sample/s CI16 IQ
and accepts GLT1 1.0 tracking descriptors on the original native source counter.
It has no fabric acquisition or legacy scoring engine. ARM owns acquisition,
retained-IQ catch-up, descriptor prediction, feedback, and loss recovery.

Existing GLR1, GLF1, GLA1 and GLT1 persisted contracts retain their meanings.
GLI1 uses new base and extension magic `0x474c4931`, version `0x00010000`,
and capability word `17` (independent IQ export and scheduled tracking).
The base and extension register layouts and snapshot field widths follow the
existing capture layout; the kernel text prefixes are `GLI1`,
`capture_abi=GLI1-1.0-upper-only`, and `capture_extension_abi=GLI1-1.0`.
The tracking page is GLT1 1.0. The manual-native and local-acquisition pages
read zero. No autonomous event device is registered by the driver.

| Native rate | IQ rate | Source index stride | FIR group delay | Initial unsupported history | Samples per native pilot |
|---|---|---|---|---|---|
| 30 MS/s | 2.5 MS/s | 12 | 636 native samples = 21.2 us | 1,272 native samples | 39,600 |
| 60 MS/s | 2.5 MS/s | 24 | 1,272 native samples = 21.2 us | 2,544 native samples | 79,200 |

Each IQ index is the newest native input to the FIR. Its signal center is
`index - group_delay`, not the DMA arrival time. Tracking uses native input
coordinates directly, without subtracting the FIR delay. A coarse estimate
must be mapped through this distinction before scheduling a native job.

Tracking runs only within an active healthy capture visit. STOP, a source gap,
or transport fault invalidates pending predictions. Completed and partial
tracking records remain available for explicit retirement. Drain IQ, retire
tracking results, clear the tracking queue, then clear the base visit. Never
hide source loss by reusing an old counter origin or a prior tracking epoch.

Build with `scripts/build_glrt_board.sh RATE NEW_DIRECTORY --iq-tracking`.
The 30-MS/s filter bank is additive and hash-frozen by
`tools/generate_glrt_thirty_ddc.py`; it does not replace an existing bank.
Component simulation and successful image generation do not by themselves
qualify live tracking. Both profiles require routed timing/CDC review and
bounded verification on the serial-bound target radio before deployment
can be reported as successful.
