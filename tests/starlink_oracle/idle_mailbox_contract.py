"""Exact allowed additive idle-mailbox delta for frozen whole-source checks."""
import re


def tokens(source):
    return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", source))


def once(source, old, new=""):
    assert source.count(old) == 1
    return source.replace(old, new, 1)


def restore_guard(source):
    source = tokens(source)
    if "parameterintegerUSE_IDLE_MAILBOX_FAULT" not in source:
        return source
    for fragment in [",parameterintegerUSE_IDLE_MAILBOX_FAULT=0",
                     "inputwireidle_mailbox_fault_now,",
                     ('if(USE_IDLE_MAILBOX_FAULT!==0&&USE_IDLE_MAILBOX_FAULT!==1)'
                      '$fatal(1,"USE_IDLE_MAILBOX_FAULTmustbezeroorone");'),
                     ("wireidle_mailbox_fault=USE_IDLE_MAILBOX_FAULT?"
                      "idle_mailbox_fault_now:mailbox_input_fault;")]:
        source = once(source, fragment)
    return once(source, "wireidle_fault_now=phase_input_fault||idle_mailbox_fault||",
                "wireidle_fault_now=phase_input_fault||mailbox_input_fault||")


def restore_service(source):
    source = tokens(source)
    if ".USE_IDLE_MAILBOX_FAULT(" not in source:
        return source
    source = once(source, ",.USE_IDLE_MAILBOX_FAULT(1)")
    return once(source, ".idle_mailbox_fault_now(output_mailbox_fault),")
