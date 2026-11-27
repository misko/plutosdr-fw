"""A persistent installation must be bound to successful exact-radio evidence."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from deploy_lan import qualification_evidence


class DeploymentGateTests(unittest.TestCase):
    def fixture(self, root):
        ram = root / 'ram-radio15'
        ram.mkdir()
        (ram / 'plan.json').write_text(json.dumps({'image_sha256': 'image', 'serial': 'radio15'}))
        (ram / 'result.json').write_text(json.dumps({'outcome': 'success'}))
        evidence = root / 'verified.json'
        evidence.write_text('{"passed": true}\n')
        report = {'schema': 'plutosdr-fw.position-scan-qualification/v1',
                  'dfu_sha256': 'image', 'serial': 'radio15', 'passed': True, 'complete_visits': 576,
                  'evidence': [{'path': evidence.name, 'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}]}
        for check in ('saved_iq_verified', 'tuning_signatures_verified', 'slot_reuse_verified',
                      'stop_restored', 'interruption_restored', 'legacy_v5_passed', 'ordinary_rx_passed'):
            report[check] = True
        return report

    def test_valid_binding_and_reject_each_failed_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self.fixture(root)
            path = root / 'qualification.json'
            path.write_text(json.dumps(report))
            self.assertEqual(len(qualification_evidence(root, {'dfu_sha256': 'image'}, 'radio15')), 2)
            for field in ('passed', 'saved_iq_verified', 'tuning_signatures_verified', 'slot_reuse_verified',
                          'stop_restored', 'interruption_restored', 'legacy_v5_passed', 'ordinary_rx_passed'):
                for invalid in (False, 'true'):
                    with self.subTest(field=field, invalid=invalid):
                        path.write_text(json.dumps(report | {field: invalid}))
                        with self.assertRaises(ValueError):
                            qualification_evidence(root, {'dfu_sha256': 'image'}, 'radio15')
            path.write_text(json.dumps(report))
            for binding, serial in (({'dfu_sha256': 'other-image'}, 'radio15'), ({'dfu_sha256': 'image'}, 'other-radio')):
                with self.assertRaises(ValueError):
                    qualification_evidence(root, binding, serial)

    def test_reject_changed_or_missing_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self.fixture(root)
            path = root / 'qualification.json'
            path.write_text(json.dumps(report))
            (root / 'verified.json').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'evidence hash'):
                qualification_evidence(root, {'dfu_sha256': 'image'}, 'radio15')
            for invalid in ([], [{'path': '../escape', 'sha256': 'bad'}]):
                path.write_text(json.dumps(report | {'evidence': invalid}))
                with self.assertRaises(ValueError):
                    qualification_evidence(root, {'dfu_sha256': 'image'}, 'radio15')


if __name__ == '__main__':
    unittest.main()
