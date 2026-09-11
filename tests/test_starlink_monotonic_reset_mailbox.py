"""Real payload mailbox recovery with the monotonic barrier explicitly enabled."""
import pytest
from tests import test_starlink_output_metadata_cdc as contract
from tests.test_starlink_reset_receipts import configure as configure_receipts

def configure(tmp_path,monkeypatch):
    configure_receipts(tmp_path,monkeypatch)
    text=contract.BENCH.read_text()
    old='starlink_pss_reset_receipt_barrier '
    assert text.count(old)==1
    contract.BENCH.write_text(text.replace(old,'starlink_pss_reset_receipt_barrier #(.MONOTONIC_OUTER_RESET(1)) ',1))

@pytest.mark.parametrize('writer,reader',[(2857,5000),(2500,5000),(5000,2857)])
@pytest.mark.parametrize('phase',[0,1,1234,4999])
def test_payload_recovery_with_stopped_clock(tmp_path,monkeypatch,writer,reader,phase):
    configure(tmp_path,monkeypatch)
    result=contract.run(tmp_path,writer,reader,phase)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'completed=13 resets=10' in result.stdout and 'OUTPUT_CDC_CONTRACT_PASS' in result.stdout

@pytest.mark.parametrize('mutant',['short_request_sync','early_ack','offered_metadata_write','capture_live_bus'])
def test_unsafe_payload_mutants_rejected(tmp_path,monkeypatch,mutant):
    configure(tmp_path,monkeypatch)
    result=contract.run(tmp_path,phase=1234,mutant=mutant)
    assert result.returncode!=0 and 'FATAL' in result.stdout and 'absolute deadline' not in result.stdout
