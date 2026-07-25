# SPF PlutoPlus direct-USB gain metadata

This firmware branch adds an 80-byte, versioned gain-metadata header before
each finite dual-RX IQ payload sent by the custom USB gadget.

The complete gadget source used by this firmware is also vendored directly in
the firmware tree:

```text
third_party/pluto-sdr-usb-gadget/
```

The gain-register reads are in `spf_gain_read.c`. The packed metadata protocol
is in `spf_gain_metadata.h`, and `thread_read.c` constructs the header and
copies the IQ payload immediately after it.

The source is published in this repository using separate branches because the
upstream firmware uses independent Git repositories for its Buildroot and USB
gadget:

```text
firmware:
  branch  v0.38_plutoplus_timestamp_gain_metadata

Buildroot snapshot:
  branch  buildroot-gain-metadata
  commit  8411051d039308f4069fe7780277311bbf177e98

USB gadget:
  branch  usb-gadget-gain-metadata
  commit  eaf850d846d8183e2345374c3d732d457ef8f8ba
```

The Buildroot package pins the gadget commit above. The firmware's `buildroot`
gitlink pins the published Buildroot snapshot, so a recursive checkout does
not require the original development machine's local source override.

The accepted RAM-boot image was:

```text
build/pluto.dfu
SHA-256:
fd8910295643b6f72d8aa30d0fa179f813a891eba452ac1605bbc529794c548a
```

That accepted image was built immediately before the source commits were
created, so its embedded version string is `a098-dirty`. Rebuilding the
published commits changes version metadata and therefore produces a different
binary hash.

The numerical gain snapshots are buffer-associated ARM register reads, not
sample-exact FPGA observations. Equal start and end indices do not prove that
gain remained stable throughout the IQ buffer.
