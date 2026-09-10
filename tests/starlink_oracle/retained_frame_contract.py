"""Causal frame evidence; no first-input/third-word or fixed vendor delay claim."""
from __future__ import annotations

import hashlib

ORIGINAL_WITNESS_SHA = "cdf025b2d72cf57a6d7ad9b78314d4eee316447ff859297a15d46efa1eb7da1b"
ORIGINAL_BENCH_SHA = "6d498ee2f8ba788e775e711753f13f85657e0c500f75ad5ffa3a6ae8cdc1575f"
ORIGINAL_RESULT_SHA = "d88ad9a86de506972a3c0a50176e09525dec4e41483ce0b7e425768e407269d4"

# Literal complete-source inverse to v4: only the frame witness/epoch additions.
ADDITIONS = (
    """integer actual_epoch_release=0,actual_config_cycle=0;
integer actual_inputs_before=0,actual_input_on=0,actual_frame_before=0,actual_frame_on=0,actual_frame_after=0;
reg actual_frame_pending=0,actual_frame_closed=0;
""",
    """      if(!actual_active||actual_epoch_release!=0||fast_cycles!=actual_admit+2)
        $fatal(1,"actual fresh reset release owner/timing");
      actual_epoch_release=fast_cycles;
""",
    """    if(actual_frame_pending)begin
      if(`D.core_aresetn!==1'b1||`D.event_frame!==1'b0||!actual_active||
         fast_cycles!=actual_frame_cycle+1)
        $fatal(1,"actual frame pulse closure/owner");
      $display("RACT_FRAME context=%0d job=%0d inverse=%0d fixture=%0d start=%0d admit=%0d release=%0d config=%0d cycle=%0d end_cycle=%0d before=%0d on=%0d after=%0d",
        context_id,actual_jobs,actual_inverse,actual_fixture,actual_start,actual_admit,
        actual_epoch_release,actual_config_cycle,actual_frame_cycle,fast_cycles,
        actual_frame_before,actual_frame_on,actual_frame_after);
      actual_frame_pending=0;actual_frame_closed=1;
    end
""",
    "      actual_epoch_release=0;actual_config_cycle=0;actual_frame_closed=0;\n",
    "        `D.core_aresetn!==1'b1||actual_epoch_release!=actual_admit+2||\n",
    "      actual_config_cycle=fast_cycles;\n",
    """    actual_inputs_before=actual_inputs;
    actual_input_on=`D.core_input_valid&&`D.core_input_ready;
""",
    """      actual_frame_before=actual_inputs_before;actual_frame_on=actual_input_on;
      actual_frame_after=actual_inputs;actual_frame_pending=1;
""",
    """      if(!actual_frame_closed||actual_frame_cycle>=fast_cycles)
        $fatal(1,"actual frame must strictly precede raw output");
""",
)
OLD_FRAME = '      if(!actual_active||actual_frames!=0||actual_inputs!=1)$fatal(1,"actual fresh frame ordinal");\n'
NEW_FRAME = """      if(!actual_active||`D.core_aresetn!==1'b1||actual_config!=1||
         actual_epoch_release!=actual_admit+2||actual_config_cycle!=actual_admit+3||
         fast_cycles<=actual_config_cycle||actual_frames!=0||actual_inputs<1||actual_raw!=0)
        $fatal(1,"actual causal frame owner/epoch/input");
"""


def inverse(text: str, *, bench=False) -> str:
    replacements = [(s, "") for s in ADDITIONS] + [
        (NEW_FRAME, OLD_FRAME),
        ("actual_frames!=1||!actual_frame_closed)", "actual_frames!=1)"),
    ]
    for new, old in replacements:
        if text.count(new) != 1:
            raise ValueError("frame inverse boundary")
        text = text.replace(new, old, 1)
    expected = ORIGINAL_BENCH_SHA if bench else ORIGINAL_WITNESS_SHA
    if hashlib.sha256(text.encode()).hexdigest() != expected:
        raise ValueError("frame complete-source inverse")
    return text


def verify_frames(records: dict, input_cycles: dict, raw_cycles: dict) -> list[dict]:
    """Independent joins to actual numerical rows, not reconstructed frame times."""
    def require(ok, message):
        if not ok:
            raise ValueError("frame " + message)

    frames = records["RACT_FRAME"]
    admits = records["RACT_ADMIT"]
    releases = records["RACT_RESET_RELEASE"]
    ends = {r["job"]: r for r in records["RACT_JOB"] + records["RACT_ABORT"]}
    require(len(frames) == len(admits) == len(releases) == 40, "inventory")
    for a, release, f in zip(admits, releases, frames, strict=True):
        require(set(f) == set("context job inverse fixture start admit release config cycle end_cycle before on after".split()), "fields")
        key = a["context"], a["inverse"], (a["start"]-1000)//447
        require((f["context"], f["job"], f["inverse"], f["fixture"], f["start"], f["admit"]) ==
                (key[0], a["job"], key[1], key[2], a["start"], a["cycle"]), "admitted identity/order")
        require(release["context"] == a["context"] and
                release["cycle"] == f["release"] == a["cycle"]+2 and
                f["config"] == a["cycle"]+3, "unique reset/config epoch join")
        require(f["release"] < f["config"] < f["cycle"] and
                f["end_cycle"] == f["cycle"]+1, "causal epoch/one-cycle pulse")
        times = input_cycles.get(key, [])
        require(bool(times), "physical input evidence missing")
        before = sum(t < f["cycle"] for t in times)
        on = sum(t == f["cycle"] for t in times)
        require(on in (0, 1) and (f["before"], f["on"], f["after"]) ==
                (before, on, before+on) and 1 <= f["after"] <= len(times),
                "physical before/on/after counter join")
        end = ends[a["job"]]
        if "publication" in end:
            require(raw_cycles.get(key) == end["raw_first"] and f["cycle"] < raw_cycles[key] and
                    f["end_cycle"] <= raw_cycles[key], "strict frame before first raw")
        else:
            require(key not in raw_cycles and f["end_cycle"] < end["cycle"], "aborted owner closure")
    return frames


# Used ONLY by old logger-regression tests. The live verifier has no legacy mode.
RESULT_ADDITIONS = (
    "from .retained_frame_contract import verify_frames\n",
    '                       "RACT_FRAME": 40,\n',
    '    frame_input_cycles = {}\n    frame_raw_cycles = {}\n',
    '                    frame_input_cycles.setdefault((context, int(stream.endswith("I")), fixture), []).append(fast)\n',
    '                    if pos == 0:\n                        frame_raw_cycles[context, int(stream.endswith("I")), fixture] = fast\n',
    '    verify_frames(records, frame_input_cycles, frame_raw_cycles)\n',
)


def inverse_result(text: str) -> str:
    for addition in RESULT_ADDITIONS:
        if text.count(addition) != 1:
            raise ValueError("frame legacy parser inverse boundary")
        text = text.replace(addition, "", 1)
    if hashlib.sha256(text.encode()).hexdigest() != ORIGINAL_RESULT_SHA:
        raise ValueError("frame legacy parser complete-source inverse")
    return text
