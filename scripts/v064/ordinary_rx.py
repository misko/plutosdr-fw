"""Save a small ordinary dual-RX control after scan ownership is released."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from pluto_plus.hardware.preflight import verify_metadata_runtime
    verify_metadata_runtime(3)
    import adi
    import numpy as np
    from pluto_plus.hardware.iio import _mute_transmit
    from pluto_plus.radio_lock import acquire_radio_lock

    serial = '104000b29905000e17000800065934759d'
    with acquire_radio_lock(serial):
        radio = adi.ad9361(uri='ip:192.168.1.15')
        if radio._ctx.attrs['hw_serial'] != serial:
            raise ValueError('ordinary RX serial mismatch')
        _mute_transmit(radio)
        tx_lo = radio._ctrl.find_channel('altvoltage1', True)
        tx_lo.attrs['powerdown'].value = '1'
        previous_size = radio.rx_buffer_size
        try:
            radio.rx_enabled_channels = [0, 1]
            radio.rx_buffer_size = 4096
            samples = np.asarray(radio.rx())
            if samples.shape != (2, 4096):
                raise ValueError('ordinary RX geometry mismatch')
            payload = np.column_stack((samples[0].real, samples[0].imag,
                                       samples[1].real, samples[1].imag)).astype('<i2').tobytes()
            if len(payload) != 32768:
                raise ValueError('ordinary RX byte count mismatch')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.with_suffix('.ci16').write_bytes(payload)
            report = {'passed': True, 'serial': serial, 'bytes': len(payload),
                      'sha256': hashlib.sha256(payload).hexdigest(),
                      'sample_rate_hz': int(radio.sample_rate), 'rx_lo_hz': int(radio.rx_lo),
                      'tx_gain_db': [float(radio.tx_hardwaregain_chan0), float(radio.tx_hardwaregain_chan1)],
                      'tx_lo_powerdown': tx_lo.attrs['powerdown'].value}
            args.output.write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report))
        finally:
            radio.rx_destroy_buffer()
            radio.rx_buffer_size = previous_size
            _mute_transmit(radio)
            tx_lo.attrs['powerdown'].value = '1'


if __name__ == '__main__':
    main()
