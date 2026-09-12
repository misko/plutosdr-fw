from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import write_evidence_archive_stream as writer


def test_roundtrip_and_no_overwrite(tmp_path):
    source = tmp_path / 'source'
    source.write_bytes(b'payload\x00' * 1000)
    output = tmp_path / 'evidence.tgz'
    result = writer.write_verified_archive(output, {'nested/source': source})
    assert result['all_members_verified'] and result['sources_unchanged']
    assert result['members'] == 2 and output.with_suffix('.json').is_file()
    original = output.read_bytes()
    with pytest.raises(ValueError):
        writer.write_verified_archive(output, {'nested/source': source})
    assert output.read_bytes() == original


@pytest.mark.parametrize('name', ['', '../bad', '/absolute', 'manifest.json'])
def test_unsafe_name_rejected(tmp_path, name):
    source = tmp_path / 'source'
    source.write_text('test')
    with pytest.raises(ValueError):
        writer.write_verified_archive(tmp_path / 'evidence.tgz', {name: source})
    assert not (tmp_path / 'evidence.tgz').exists()


def test_symlink_rejected(tmp_path):
    source = tmp_path / 'source'
    source.write_text('test')
    alias = tmp_path / 'alias'
    alias.symlink_to(source)
    with pytest.raises(ValueError):
        writer.write_verified_archive(tmp_path / 'evidence.tgz', {'source': alias})


def test_changed_source_cannot_receive_receipt(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.write_text('original')
    original_verify = writer.verify
    def mutate_after_readback(path):
        result = original_verify(path)
        source.write_text('mutated!')
        return result
    monkeypatch.setattr(writer, 'verify', mutate_after_readback)
    output = tmp_path / 'evidence.tgz'
    with pytest.raises(ValueError, match='source changed'):
        writer.write_verified_archive(output, {'source': source})
    assert output.is_file() and not output.with_suffix('.json').exists()
