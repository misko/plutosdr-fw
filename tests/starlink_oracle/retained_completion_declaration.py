"""Strict two-edit inverse of the observed implicit-net declaration correction."""
import hashlib

PATH = "hdl/library/starlink_pss_acquisition/retained_output/starlink_pss_fft_retained_output_impl.v"
ORIGINAL_SHA = "3d494d7ce8a6cc8f863b4d1ec0b465c084082d3eb64956c581488245042d6da5"
ANCHOR = "  wire producer_transfer_receipt, reader_release;\n"
DECLARATION = "  wire completion_accept;\n"
OLD = "  wire completion_accept = state == ACK_DRAIN && !completion_receipt &&\n"
NEW = "  assign completion_accept = state == ACK_DRAIN && !completion_receipt &&\n"


def inverse(text: str) -> str:
    if text.count(ANCHOR + DECLARATION) != 1 or text.count(NEW) != 1 or OLD in text:
        raise ValueError("completion declaration inverse boundaries")
    restored = text.replace(ANCHOR + DECLARATION, ANCHOR, 1).replace(NEW, OLD, 1)
    if hashlib.sha256(restored.encode()).hexdigest() != ORIGINAL_SHA:
        raise ValueError("completion declaration whole-source inverse")
    return restored
