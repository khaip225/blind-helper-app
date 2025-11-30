import time
import numpy as np
from typing import Dict, Any

from config import MAX_AMP


class VoiceActivityDetector:
    """Phát hiện hoạt động giọng nói (Voice Activity Detection)"""

    def __init__(self, sample_rate: int = 48000, silence_threshold: float = 0.02,
                 silence_duration: float = 5.0, min_speech_duration: float = 0.5):
        """
        Args:
            sample_rate: Tần số lấy mẫu
            silence_threshold: Ngưỡng âm lượng để coi là im lặng (0.0-1.0)
            silence_duration: Thời gian im lặng để kết thúc thu âm (giây)
            min_speech_duration: Thời gian nói tối thiểu để bắt đầu thu âm (giây)
        """
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.min_speech_duration = min_speech_duration

        # Trạng thái
        self.is_speaking = False
        self.speech_start_time = None
        self.silence_start_time = None
        self.audio_buffer = []

    def process_audio_chunk(self, audio_chunk: np.ndarray) -> Dict[str, Any]:
        """
        Xử lý chunk âm thanh để phát hiện giọng nói

        Args:
            audio_chunk: Chunk âm thanh (numpy array)

        Returns:
            Dict với thông tin trạng thái
        """
        # Tính RMS (Root Mean Square) để đo âm lượng
        rms = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))

        current_time = time.time()

        # Phát hiện giọng nói
        if rms > self.silence_threshold:
            if not self.is_speaking:
                # Bắt đầu nói
                self.is_speaking = True
                self.speech_start_time = current_time
                self.silence_start_time = None
                self.audio_buffer = [audio_chunk]
                print(f"��️ Bắt đầu phát hiện giọng nói (RMS: {rms:.4f})")
            else:
                # Đang nói - thêm vào buffer
                self.audio_buffer.append(audio_chunk)
                self.silence_start_time = None
        else:
            # Im lặng
            if self.is_speaking:
                if self.silence_start_time is None:
                    self.silence_start_time = current_time
                elif current_time - self.silence_start_time >= self.silence_duration:
                    # Kết thúc nói
                    speech_duration = current_time - self.speech_start_time
                    if speech_duration >= self.min_speech_duration:
                        # Có đủ thời gian nói
                        # Chuẩn hóa biên độ âm thanh trước khi nối
                        normalized_buffers = []
                        for chunk in self.audio_buffer:
                            # Chuẩn hóa biên độ để tránh tiếng rè
                            # max_val = np.max(np.abs(chunk))
                            # if max_val > MAX_AMP:  # Nếu biên độ quá lớn
                            #     chunk = chunk * (MAX_AMP / max_val)
                            normalized_buffers.append(chunk)

                        audio_data = np.concatenate(normalized_buffers)

                        # Đảm bảo audio_data là mảng 1 chiều trước khi áp dụng bộ lọc
                        if len(audio_data.shape) > 1:
                            # Nếu là mảng nhiều chiều, chỉ lấy kênh đầu tiên
                            audio_data = audio_data.flatten()

                        # max_amp = np.max(np.abs(audio_data))
                        # if max_amp > MAX_AMP:
                        #     audio_data = audio_data * (MAX_AMP / max_amp)

                        self.is_speaking = False
                        self.speech_start_time = None
                        self.silence_start_time = None
                        self.audio_buffer = []

                        print(f"✅ Hoàn tất thu âm ({speech_duration:.1f}s)")
                        return {
                            'action': 'speech_complete',
                            'audio_data': audio_data,
                            'duration': speech_duration,
                            'rms': rms
                        }
                    else:
                        # Thời gian nói quá ngắn - bỏ qua
                        print(
                            f"⚠️ Thời gian nói quá ngắn ({speech_duration:.1f}s) - bỏ qua")
                        self.is_speaking = False
                        self.speech_start_time = None
                        self.silence_start_time = None
                        self.audio_buffer = []
            else:
                # Đang im lặng - thêm vào buffer để phát hiện
                if len(self.audio_buffer) < 10:  # Giữ buffer nhỏ
                    self.audio_buffer.append(audio_chunk)
                else:
                    self.audio_buffer = self.audio_buffer[1:] + [audio_chunk]

        return {
            'action': 'listening' if not self.is_speaking else 'speaking',
            'is_speaking': self.is_speaking,
            'rms': rms,
            'speech_duration': current_time - self.speech_start_time if self.is_speaking else 0
        }
