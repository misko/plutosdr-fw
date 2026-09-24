import hashlib, json, subprocess
from pathlib import Path
import pytest
from scripts.release_v056 import campaign, prepare
ROOT=Path(__file__).resolve().parents[1]; VERSION="v0.56-plutoplus-spf-adaptive-runtime-rates"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs(tmp):
    image=tmp/"x.dfu";image.write_bytes(b"x"); source=ROOT/"manifests/adaptive-runtime-rates-v056-source.yaml"; commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(); candidate=tmp/"candidate.json";candidate.write_text(json.dumps({"firmware":VERSION,"firmware_source_commit":commit,"asset_sha256":sha(image),"source_manifest_sha256":sha(source)})); bind=tmp/"binding.json";prepare.write_new(bind,prepare.prepare(repo=ROOT,source_manifest=source,candidate_path=candidate,image=image,expected_source=commit)); inv=tmp/"inventory.json";inv.write_text(json.dumps({"schema":"plutosdr-fw.v056-radio-inventory/v1","radios":{campaign.SERIALS[0]:"ip:192.168.1.18",campaign.SERIALS[1]:"ip:192.168.1.19"}})); tool=tmp/"tool.py";tool.write_text("# b1097fb\n");return bind,inv,tool,tmp/"ledger.jsonl"
def make_plan(tmp):
    bind,inv,tool,ledger=inputs(tmp);p=tmp/"plan.json";campaign.write_new(p,campaign.plan(bind,inv,tool,ledger,"v056-test"));return p
def test_plan_uses_one_exact_host_interface_and_fresh_ledger(tmp_path):
    p=make_plan(tmp_path); plan=json.loads(p.read_text());assert len(plan["cells"])==32 and plan["budget_seconds"]==11520 and not Path(plan["ledger"]).exists()
    required={"--cell","--output","--ledger","--candidate","--inventory","--campaign-id","--budget-seconds","--serial","--uri","--rate-hz","--rx-mask","--duration-seconds"}
    assert all(required <= set(cell["command"]) for cell in plan["cells"]);assert {c["rx_mask"] for c in plan["cells"] if c["rate_hz"] in (2500000,5000000,7500000,8000000)}=={3}
def test_existing_ledger_is_refused(tmp_path):
    bind,inv,tool,ledger=inputs(tmp_path);ledger.write_text("")
    with pytest.raises(ValueError,match="fresh"):campaign.plan(bind,inv,tool,ledger,"id")
def rows(plan):
    out=[]
    for cell in plan["cells"]:out.append({"schema":"org.leo.issue111.adaptive-ledger-row/v1","campaign_id":plan["campaign_id"],"serial":cell["serial"],"cell":cell["cell"],"reserved_seconds":360})
    return out
def report(cell,plan,ledger_hash):return {"schema":"org.leo.issue111.adaptive-capture/v1","passed":True,"cell":cell["cell"],"serial":cell["serial"],"uri":cell["uri"],"rate_hz":cell["rate_hz"],"rx_mask":cell["rx_mask"],"duration_seconds":300,"candidate_manifest_sha256":plan["candidate_manifest_sha256"],"inventory_sha256":plan["inventory_sha256"],"ledger_sha256":ledger_hash,"counter_continuity_passed":True,"iq_geometry_passed":True,"receiver_restored":True}
def test_verdict_binds_ledger_reports_and_cold_cycle(tmp_path):
    p=make_plan(tmp_path);plan=json.loads(p.read_text());ledger=Path(plan["ledger"]);raw=b""; prefixes={}
    with ledger.open("wb") as f:
        for row in rows(plan):line=(json.dumps(row,sort_keys=True)+"\n").encode();f.write(line);raw+=line;prefixes[(row["serial"],row["cell"])]=hashlib.sha256(raw).hexdigest()
    evidence=tmp_path/"evidence"
    for cell in plan["cells"]:
        target=evidence/cell["output"];target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report(cell,plan,prefixes[(cell["serial"],cell["cell"])])))
    cold=tmp_path/"cold.json";cold.write_text(json.dumps({"schema":"plutosdr-fw.v056-physical-cold-cycle-receipt/v1","serial":campaign.SERIALS[0],"operator":"op","all_power_removed":True,"power_reconnected":True,"rediscovery_passed":True,"firmware":plan["firmware"],"image_sha256":plan["image_sha256"],"source_commit":plan["source_commit"],"power_off_utc":"2026-09-24T00:00:00Z","power_on_utc":"2026-09-24T00:01:00Z"}))
    assert campaign.validate(p,evidence,cold)["passed"] is True
    cold_data=json.loads(cold.read_text());cold_data.pop("power_on_utc");cold.write_text(json.dumps(cold_data));assert campaign.validate(p,evidence,cold)["passed"] is False
def test_emit_is_dry_run(tmp_path,capsys):
    p=make_plan(tmp_path);assert campaign.emit_or_run(p,tmp_path/"evidence") == 0;assert "--budget-seconds 11520" in capsys.readouterr().out
def test_emit_refuses_a_partial_ledger(tmp_path):
    p=make_plan(tmp_path); plan=json.loads(p.read_text());Path(plan["ledger"]).write_text("partial\n")
    with pytest.raises(FileExistsError,match="ledger"):
        campaign.emit_or_run(p,tmp_path/"evidence")
