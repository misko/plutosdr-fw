"""Assemble public qualification evidence without private device backups."""
import hashlib
import json
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
E = BASE / 'evidence'
OUT = BASE.parents[1] / 'reports/issue97/v0.50'
manifest = json.loads((BASE / 'build/counter-rx-v1.json').read_text())
serial, version = manifest['serial'], manifest['firmware']
files = []
cells = []
for path in sorted(E.glob('*.json')):
    if path.name.startswith(('candidate-1r1t-', 'paired-', 'persistent-paired-')):
        result = json.loads(path.read_text())
        assert result['serial'] == serial and result['firmware'] == version
        assert result['restored'] and result['restored_gain'] and result['restored_queue']
        for cell in result['cells']:
            assert cell['outcome'] == 'completed'
            frames = cell['frames']
            missing = sum(f['missing'] for f in frames)
            cells.append({'report':path.name, 'rate_hz':cell['sample_rate'], 'frames':len(frames),
                          'samples_per_frame':frames[0]['end']-frames[0]['first'],
                          'missing_samples':missing, 'allocated_kernel_buffers':cell['allocated_kernel_buffers']})
        files.append(path)
for name in ('lifecycle.json', 'disconnect.json', 'persistent-public-capture.json', 'persistent-reboot-1r1t.json', 'persistent-reboot-2r2t.json'):
    path = E / name
    data = json.loads(path.read_text())
    if name.startswith('persistent-reboot'):
        assert data['serial'] == serial and data['firmware'] == version
        assert data['fit_sha256'] == manifest['fit_sha256']
    if name == 'persistent-public-capture.json':
        assert data['identity']['firmware_version'] == version and data['serial'] == serial
        assert data['restored'] and data['queue_restored']
        for cell in data['cells']:
            assert cell['allocated_kernel_buffers'] == 50 and len(cell['frames']) == 30
            assert all(f['missing'] == 0 for f in cell['frames'])
    files.append(path)
receipts = []
for name in ('ram-2r2t-result.json', 'ram-1r1t-result.json', 'persistent-result.json'):
    path = E / name
    result = json.loads(path.read_text())
    assert result['outcome'] == 'success' and result['returned_serial'] == serial and result['returned_firmware'] == version
    receipt = Path(result['receipt_path'])
    files += [path, receipt]
    receipts.append({'phase':name, 'receipt_id':result['receipt_id'], 'sha256':hashlib.sha256(receipt.read_bytes()).hexdigest()})
OUT.mkdir(parents=True, exist_ok=True)
raw = OUT / 'hardware'
raw.mkdir(exist_ok=True)
for path in files:
    shutil.copyfile(path, raw / path.name)
report = manifest | {
    'schema':'plutosdr-fw.counter-rx-v1-qualification', 'schema_version':1,
    'hardware_qualified':True, 'persistent_qualified':True, 'persistent_reboot_qualified':True,
    'cold_power_cycle_qualified':False, 'units_tested':1, 'final_mode':'1r1t',
    'cells':cells, 'receipts':receipts,
    'offline_tests':{'firmware':1516,'ppu':3449,'native_suites':14},
    'limitations':[
        'Finite 60 MS/s capture does not qualify continuous lossless 240 MB/s Ethernet streaming.',
        '60 MS/s uses 50 MHz analog bandwidth; no analog RF accuracy or detector qualification.',
        'Counter metadata has no paired AGC, gain or RSSI validity.',
        'Only this single serial was tested.',
        'Known FunctionFS supervisor USB unbinding after forced iiOD death required targeted rebind.',
        'Timestamp packer/XPM functional simulation has startup assertion warnings.',
    ],
}
(OUT / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
