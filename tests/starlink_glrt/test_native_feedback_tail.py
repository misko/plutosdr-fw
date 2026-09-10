"""Partial batches use the existing horizon without extrapolating farther."""
import pytest

from tests.starlink_glrt.test_native_controller import Radio, controller, pilot_words
from tests.starlink_glrt.test_native_journal import journal
from tools.starlink_glrt_native_journal import review


class IntermittentRadio(Radio):
    def __init__(self, lib, words, resume_at):
        super().__init__(lib, words, frames=128)
        self.resume_at = resume_at

    def advance(self, samples=3000):
        before = len(self.queue)
        super().advance(samples)
        for words in self.queue[before:]:
            frame = words[1]
            if frame >= 20 and (self.resume_at is None or frame < self.resume_at):
                words[9:25] = [0] * 16


@pytest.mark.parametrize('resume_at', [48, 52, None])
def test_returning_pilot_can_only_restore_feedback_before_original_expiry(controller, pilot_words, resume_at):
    radio = IntermittentRadio(controller, pilot_words, resume_at)
    assert radio.run() == (0 if resume_at == 48 else -4)
    checked = review(journal(radio), epoch=3)
    assert not radio.pending and not radio.queue and not radio.valid
    assert checked['drained'].cancelled == 0
    assert any(b.repeats < 16 for b in radio.descriptors[1:])
    if resume_at == 48:
        assert len(checked['heads']) == 128
        assert [e['rejection'] == 0 for e in checked['estimates']] == [i < 20 or i >= 48 for i in range(128)]
    else:
        assert len(checked['heads']) == 52
        assert checked['supported'] == 20
        assert checked['estimates'][-1]['frame'] == 51
    # Audit authorization using only estimates retained before each submission.
    last_supported = None
    for kind, name, body in radio.events:
        if (kind, name) == ('retain', 'estimate'):
            fields = body.split()
            if int(fields[8]) == 0:
                last_supported = int(fields[2])
        if (kind, name) == ('retain', 'descriptor'):
            fields = body.split()
            assert fields[0] == b'frame'
            first, repeats = int(fields[1]), int(fields[-2], 16)
            if first:
                assert last_supported is not None
                assert first + repeats - 1 <= last_supported + 32
