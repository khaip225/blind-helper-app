"""
Audio Utilities
===============
"""

import sounddevice as sd
import numpy as np
from typing import List, Tuple


def get_supported_sample_rates(device_id: int) -> List[int]:
    """
    Lấy danh sách sample rates được hỗ trợ bởi device

    Args:
        device_id: ID của audio device

    Returns:
        List các sample rates được hỗ trợ
    """
    supported_rates = []
    test_rates = [8000, 16000, 22050, 44100, 48000, 96000]

    for rate in test_rates:
        try:
            with sd.InputStream(
                device=device_id,
                channels=1,
                samplerate=rate,
                dtype='int16',
                blocksize=1024
            ) as stream:
                supported_rates.append(rate)
        except:
            pass

    return supported_rates


def get_best_sample_rate(device_id: int) -> int:
    """
    Tìm sample rate tốt nhất cho device

    Args:
        device_id: ID của audio device

    Returns:
        Sample rate tốt nhất (ưu tiên 48kHz, 44.1kHz, 22kHz)
    """
    supported_rates = get_supported_sample_rates(device_id)

    # Ưu tiên theo thứ tự
    preferred_rates = [48000, 44100, 22050, 16000, 8000]

    for rate in preferred_rates:
        if rate in supported_rates:
            return rate

    # Fallback về rate đầu tiên được hỗ trợ
    return supported_rates[0] if supported_rates else 48000


def test_audio_device(device_id: int) -> dict:
    """
    Test audio device và trả về thông tin chi tiết

    Args:
        device_id: ID của audio device

    Returns:
        Dict với thông tin device
    """
    try:
        device_info = sd.query_devices(device_id)
        supported_rates = get_supported_sample_rates(device_id)
        best_rate = get_best_sample_rate(device_id)

        return {
            'device_id': device_id,
            'name': device_info['name'],
            'max_input_channels': device_info['max_input_channels'],
            'max_output_channels': device_info['max_output_channels'],
            'default_samplerate': device_info['default_samplerate'],
            'supported_rates': supported_rates,
            'recommended_rate': best_rate,
            'status': 'OK'
        }
    except Exception as e:
        return {
            'device_id': device_id,
            'status': 'ERROR',
            'error': str(e)
        }


def find_audio_devices() -> List[dict]:
    """
    Tìm tất cả audio devices và test chúng

    Returns:
        List các device info
    """
    devices = sd.query_devices()
    device_list = []

    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0 or device['max_output_channels'] > 0:
            device_info = test_audio_device(i)
            device_list.append(device_info)

    return device_list


def print_audio_devices():
    """In thông tin tất cả audio devices"""
    print("=== Audio Devices ===")
    devices = find_audio_devices()

    for device in devices:
        print(f"\nDevice {device['device_id']}: {device['name']}")
        print(f"  Status: {device['status']}")

        if device['status'] == 'OK':
            print(f"  Input channels: {device['max_input_channels']}")
            print(f"  Output channels: {device['max_output_channels']}")
            print(f"  Default sample rate: {device['default_samplerate']}")
            print(f"  Supported rates: {device['supported_rates']}")
            print(f"  Recommended rate: {device['recommended_rate']}")
        else:
            print(f"  Error: {device['error']}")


if __name__ == "__main__":
    print_audio_devices()
