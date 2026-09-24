#!/usr/bin/env python3
"""Dry-run-first v0.56 qualification campaign; never deploys or discovers."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shlex, subprocess
from datetime import datetime
from pathlib import Path

SERIALS = ("1040007c4a94000211000b009186843ef2", "104000b29905000e17000800065934759d")
V056 = "v0.56-plutoplus-spf-adaptive-runtime-rates"; DURATION = 300; BUDGET = 11_520
RATES = (("dual-counter-gap", 2_500_000, 3, 10), ("runtime-rate", 5_000_000, 3, 1), ("runtime-rate", 7_500_000, 3, 1), ("runtime-rate", 8_000_000, 3, 1), ("legacy-rate", 10_000_000, 1, 1), ("legacy-rate", 15_000_000, 1, 1), ("legacy-rate", 20_000_000, 1, 1))

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def obj(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text());
    if not isinstance(value, dict): raise ValueError("JSON object required")
    return value
def binding(path: Path) -> dict[str, object]:
    value = obj(path)
    if value.get("schema") != "plutosdr-fw.v056-qualification-binding/v1" or value.get("firmware") != V056 or not re.fullmatch(r"[0-9a-f]{40}", str(value.get("source_commit"))): raise ValueError("exact v0.56 binding required")
    if not Path(str(value.get("image", ""))).is_file() or sha(Path(str(value["image"]))) != value.get("image_sha256"): raise ValueError("bound image changed")
    return value
def inventory(path: Path) -> dict[str, str]:
    value = obj(path); radios = value.get("radios")
    if value.get("schema") != "plutosdr-fw.v056-radio-inventory/v1" or not isinstance(radios, dict) or set(radios) != set(SERIALS) or any(not isinstance(uri, str) or not uri.startswith("ip:") or not uri[3:] for uri in radios.values()): raise ValueError("exact inventory required")
    return radios
def write_new(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream: json.dump(value, stream, indent=2, sort_keys=True); stream.write("\n")

def plan(binding_path: Path, inventory_path: Path, tool: Path, ledger: Path, campaign_id: str) -> dict[str, object]:
    bound = binding(binding_path); radios = inventory(inventory_path)
    if not tool.is_file() or ledger.exists() or not campaign_id: raise ValueError("host tool must exist, ledger must be fresh, and campaign id is required")
    candidate = Path(str(bound["candidate_manifest"])); cells=[]
    for serial in SERIALS:
        for kind, rate, mask, repetitions in RATES:
            for attempt in range(1, repetitions + 1):
                name = f"{kind}-{rate}-{attempt:02d}"; output=f"captures/{serial}/{name}.json"
                command=["python3", str(tool.resolve()), "--cell", name, "--output", output, "--ledger", str(ledger.resolve()), "--candidate", str(candidate.resolve()), "--inventory", str(inventory_path.resolve()), "--campaign-id", campaign_id, "--budget-seconds", str(BUDGET), "--serial", serial, "--uri", radios[serial], "--rate-hz", str(rate), "--rx-mask", str(mask), "--duration-seconds", str(DURATION)]
                cells.append({"cell":name,"kind":kind,"serial":serial,"uri":radios[serial],"rate_hz":rate,"rx_mask":mask,"duration_seconds":DURATION,"output":output,"command":command})
    if len(cells) != 32: raise AssertionError("campaign geometry changed")
    return {"schema":"plutosdr-fw.v056-counter-gap-campaign/v3","binding":str(binding_path.resolve()),"binding_sha256":sha(binding_path),"inventory":str(inventory_path.resolve()),"inventory_sha256":sha(inventory_path),"host_tool":str(tool.resolve()),"host_tool_sha256":sha(tool),"ledger":str(ledger.resolve()),"campaign_id":campaign_id,"budget_seconds":BUDGET,"firmware":bound["firmware"],"image_sha256":bound["image_sha256"],"source_commit":bound["source_commit"],"candidate_manifest_sha256":bound["candidate_manifest_sha256"],"cells":cells}

def load_campaign(path: Path) -> dict[str, object]:
    value=obj(path)
    if value.get("schema") != "plutosdr-fw.v056-counter-gap-campaign/v3": raise ValueError("campaign schema")
    for label in ("binding","inventory","host_tool"):
        item=Path(str(value[label])); expected=value[f"{label}_sha256"]
        if not item.is_file() or sha(item)!=expected: raise ValueError(f"{label} changed")
    binding(Path(str(value["binding"]))); inventory(Path(str(value["inventory"])))
    if value.get("budget_seconds") != BUDGET or len(value.get("cells",[])) != 32: raise ValueError("campaign budget or cells invalid")
    return value

def ledger_hashes(path: Path, campaign: dict[str, object]) -> dict[tuple[str,str], str]:
    lines=path.read_bytes().splitlines(keepends=True)
    if len(lines)!=32: raise ValueError("ledger must have exactly 32 rows")
    prefixes=b""; found={}
    for line in lines:
        prefixes += line; row=json.loads(line)
        key=(row.get("serial"),row.get("cell"))
        if row.get("schema")!="org.leo.issue111.adaptive-ledger-row/v1" or row.get("campaign_id")!=campaign["campaign_id"] or row.get("reserved_seconds")!=360 or key in found: raise ValueError("invalid ledger reservation")
        found[key]=hashlib.sha256(prefixes).hexdigest()
    if set(found) != {(cell["serial"],cell["cell"]) for cell in campaign["cells"]} or sum(json.loads(line)["reserved_seconds"] for line in lines)!=BUDGET: raise ValueError("ledger does not match campaign")
    return found
def report_ok(report: dict[str,object], cell: dict[str,object], campaign: dict[str,object], ledger: dict[tuple[str,str],str]) -> bool:
    return (report.get("schema")=="org.leo.issue111.adaptive-capture/v1" and report.get("passed") is True and all(report.get(key)==cell[key] for key in ("cell","serial","uri","rate_hz","rx_mask","duration_seconds")) and report.get("candidate_manifest_sha256")==campaign["candidate_manifest_sha256"] and report.get("inventory_sha256")==campaign["inventory_sha256"] and report.get("ledger_sha256")==ledger[(cell["serial"],cell["cell"])] and report.get("counter_continuity_passed") is True and report.get("iq_geometry_passed") is True and report.get("receiver_restored") is True)
def cold_ok(path: Path,campaign:dict[str,object])->bool:
    row=obj(path)
    try:
        off = datetime.fromisoformat(str(row["power_off_utc"]).replace("Z", "+00:00"))
        on = datetime.fromisoformat(str(row["power_on_utc"]).replace("Z", "+00:00"))
    except (KeyError, ValueError): return False
    return (row.get("schema")=="plutosdr-fw.v056-physical-cold-cycle-receipt/v1" and row.get("all_power_removed") is True and row.get("power_reconnected") is True and row.get("rediscovery_passed") is True and row.get("firmware")==campaign["firmware"] and row.get("image_sha256")==campaign["image_sha256"] and row.get("source_commit")==campaign["source_commit"] and row.get("serial") in SERIALS and isinstance(row.get("operator"),str) and bool(row["operator"]) and off.tzinfo is not None and on.tzinfo is not None and on > off)
def validate(plan_path:Path,evidence:Path,cold:Path)->dict[str,object]:
    campaign=load_campaign(plan_path); failures=[]; digests={}
    try: hashes=ledger_hashes(Path(str(campaign["ledger"])),campaign)
    except (OSError,ValueError,json.JSONDecodeError): hashes={}; failures=[cell["output"] for cell in campaign["cells"]]
    for cell in campaign["cells"]:
        path=evidence/cell["output"]
        try:
            report=obj(path); digests[cell["output"]]=sha(path); ok=bool(hashes) and report_ok(report,cell,campaign,hashes)
        except (OSError,ValueError,json.JSONDecodeError): ok=False
        if not ok and cell["output"] not in failures: failures.append(cell["output"])
    try: cold_passed=cold_ok(cold,campaign)
    except (OSError,ValueError,json.JSONDecodeError): cold_passed=False
    return {"schema":"plutosdr-fw.v056-counter-gap-verdict/v3","passed":not failures and cold_passed,"failed_reports":failures,"physical_cold_cycle_passed":cold_passed,"reports":digests,"campaign_sha256":sha(plan_path),"prior_incident_attributed":False}
def emit_or_run(plan:Path,evidence:Path,execute:bool=False)->int:
    campaign=load_campaign(plan)
    if Path(str(campaign["ledger"])).exists(): raise FileExistsError("ledger must be absent before first campaign run")
    for cell in campaign["cells"]:
        output=evidence/cell["output"]
        if output.exists(): raise FileExistsError(f"immutable output exists: {output}")
        command=[str(output) if item==cell["output"] else item for item in cell["command"]]; print(shlex.join(command))
        if execute: output.parent.mkdir(mode=0o700,parents=True,exist_ok=True); subprocess.run(command,check=True)
    return 0
def main()->int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="action",required=True); p=sub.add_parser("plan")
    for name in ("binding","inventory","host-tool","ledger","output"):p.add_argument(f"--{name}",type=Path,required=True)
    p.add_argument("--campaign-id",required=True); v=sub.add_parser("validate")
    for name in ("plan","evidence","cold-cycle","output"):v.add_argument(f"--{name}",type=Path,required=True)
    e=sub.add_parser("emit");e.add_argument("--plan",type=Path,required=True);e.add_argument("--evidence",type=Path,required=True);e.add_argument("--execute",action="store_true");a=parser.parse_args()
    if a.action=="emit":return emit_or_run(a.plan,a.evidence,a.execute)
    value=plan(a.binding,a.inventory,a.host_tool,a.ledger,a.campaign_id) if a.action=="plan" else validate(a.plan,a.evidence,a.cold_cycle);write_new(a.output,value);return int(a.action=="validate" and not value["passed"])
if __name__=="__main__":raise SystemExit(main())
