import soundfile as sf
import os
import sounddevice as sd
import numpy as np
import tempfile
from scipy import signal
from container import container
from log import setup_logger
import queue
import threading

logger = setup_logger(__name__)


def find_device_index_by_name(keyword, kind='output'):
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if keyword.lower() in dev['name'].lower():
            if kind == 'output' and dev['max_output_channels'] > 0:
                return i
    return None


class VoiceSpeaker:
    def __init__(self, speaker_name):
        self.speaker_index = find_device_index_by_name(
            speaker_name, kind='output')
        if self.speaker_index is None:
            raise ValueError(f"Không tìm thấy loa nào chứa '{speaker_name}'!")
        logger.info(f"🔊 Speaker index (PulseAudio): {self.speaker_index}")
        container.register("speaker", self)
        # Streaming state
        self._out_stream = None
        self._out_queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=100)
        self._stream_rate = None
        self._stream_channels = None
        self._stream_blocksize = None
        self._stream_lock = threading.Lock()

    def play_file(self, file_path: str):
        """Phát âm thanh từ file (wav, flac, ogg, mp3 nếu có soundfile hỗ trợ)."""
        if not os.path.exists(file_path):
            logger.error(f"❌ File không tồn tại: {file_path}", exc_info=True)
            return

        try:
            data, samplerate = sf.read(file_path, dtype='float32')
            # Đảm bảo samplerate phù hợp với thiết bị
            if samplerate != 44100:
                logger.info(f"Chuyển đổi sample rate từ {samplerate} sang 44100Hz")
                # Nếu sample rate khác 44100, thực hiện resampling
                samples = len(data)
                new_samples = int(samples * 44100 / samplerate)
                data = signal.resample(data, new_samples)
                samplerate = 44100
                
            sd.play(data, device=self.speaker_index)
            sd.wait()  # Chờ phát xong
        except Exception as e:
            logger.error(f"⚠️ Lỗi khi phát file: {e}", exc_info=True)

    def play_audio_data(self, audio_data: bytes, sample_rate: int = 44100):
        """
        Phát âm thanh từ dữ liệu raw
        """
        try:
            if type(audio_data) == bytes:
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
            else:
                audio_array = audio_data

            # Tạo file WAV tạm với soundfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                # Lưu với soundfile để có header WAV đúng
                sf.write(temp_file.name, audio_array,
                        sample_rate, subtype='PCM_16')
                temp_file.flush()

                self.play_file(temp_file.name)

                # Cleanup
                os.unlink(temp_file.name)

            logger.info(
                f"🔊 Phát âm thanh thành công - {len(audio_data)} bytes với sample rate {sample_rate}")
        except Exception as e:
            logger.error(f"❌ Lỗi phát âm thanh: {e}", exc_info=True)
    
    def play_audio_array(self, audio_array: np.ndarray, sample_rate: int = 44100, channels: int = 1):
        """
        Phát âm thanh từ numpy array (real-time streaming)
        
        Args:
            audio_array: numpy array với shape (samples, channels) hoặc (samples,) 
            sample_rate: sample rate của audio
            channels: số channels (1=mono, 2=stereo)
        """
        try:
            # Đảm bảo shape đúng
            if audio_array.ndim == 1:
                # Mono: reshape thành (samples, 1)
                audio_array = audio_array.reshape(-1, 1)
            elif audio_array.ndim == 2 and audio_array.shape[1] != channels:
                # Nếu channels không khớp, điều chỉnh
                if channels == 1 and audio_array.shape[1] == 2:
                    # Stereo -> Mono: lấy left channel
                    audio_array = audio_array[:, 0:1]
                elif channels == 2 and audio_array.shape[1] == 1:
                    # Mono -> Stereo: duplicate
                    audio_array = np.repeat(audio_array, 2, axis=1)
            
            # Resample nếu sample rate khác 44100
            if sample_rate != 44100:
                # Resample từng channel
                if audio_array.shape[1] == 1:
                    # Mono
                    samples = len(audio_array)
                    new_samples = int(samples * 44100 / sample_rate)
                    audio_array = signal.resample(audio_array, new_samples)
                else:
                    # Stereo: resample từng channel riêng
                    left = signal.resample(audio_array[:, 0], int(len(audio_array) * 44100 / sample_rate))
                    right = signal.resample(audio_array[:, 1], int(len(audio_array) * 44100 / sample_rate))
                    audio_array = np.column_stack([left, right])
                sample_rate = 44100
            
            # Convert về float32 nếu cần (sd.play yêu cầu float32)
            if audio_array.dtype == np.int16:
                audio_array = audio_array.astype(np.float32) / 32767.0
            elif audio_array.dtype == np.int32:
                audio_array = audio_array.astype(np.float32) / 2147483647.0
            elif audio_array.dtype != np.float32:
                audio_array = audio_array.astype(np.float32)
            
            # Phát audio (non-blocking)
            sd.play(audio_array, samplerate=sample_rate, device=self.speaker_index)
            
        except Exception as e:
            logger.error(f"❌ Lỗi phát audio array: {e}", exc_info=True)

    # -------- Streaming API dành cho WebRTC ----------
    def _ensure_output_stream(self, sample_rate: int, channels: int, block_ms: int = 20):
        with self._stream_lock:
            desired_blocksize = max(128, int(sample_rate * block_ms / 1000))
            if (self._out_stream is not None and
                self._stream_rate == sample_rate and
                self._stream_channels == channels and
                self._stream_blocksize == desired_blocksize):
                return
            # Recreate stream if params changed
            if self._out_stream is not None:
                try:
                    self._out_stream.stop()
                    self._out_stream.close()
                except Exception:
                    pass
                self._out_stream = None
                # Clear queue
                while not self._out_queue.empty():
                    try:
                        self._out_queue.get_nowait()
                    except Exception:
                        break
            def callback(outdata, frames, time_info, status):
                if status:
                    logger.debug(f"OutputStream status: {status}")
                needed = frames
                channels_local = channels
                # Gather from queue
                chunks = []
                remaining = needed
                try:
                    while remaining > 0:
                        chunk = self._out_queue.get_nowait()
                        if chunk.ndim == 1:
                            chunk = chunk.reshape(-1, channels_local)
                        take = min(remaining, len(chunk))
                        chunks.append(chunk[:take])
                        # If chunk longer than needed, push remainder back
                        if take < len(chunk):
                            rest = chunk[take:]
                            try:
                                self._out_queue.put_nowait(rest)
                            except Exception:
                                pass
                        remaining -= take
                except queue.Empty:
                    pass
                if chunks:
                    data = np.vstack(chunks)
                else:
                    data = np.zeros((needed, channels_local), dtype=np.float32)
                # Pad if still short
                if len(data) < needed:
                    pad = np.zeros((needed - len(data), channels_local), dtype=np.float32)
                    data = np.vstack([data, pad])
                outdata[:] = data
            try:
                self._out_stream = sd.OutputStream(
                    device=self.speaker_index,
                    samplerate=sample_rate,
                    channels=channels,
                    dtype='float32',
                    blocksize=desired_blocksize,
                    callback=callback
                )
                self._out_stream.start()
                self._stream_rate = sample_rate
                self._stream_channels = channels
                self._stream_blocksize = desired_blocksize
                logger.info(f"🔊 OutputStream started: {sample_rate}Hz, ch={channels}, block={desired_blocksize}")
            except Exception as e:
                logger.error(f"❌ Không mở được OutputStream: {e}", exc_info=True)

    def start_stream(self, sample_rate: int = 48000, channels: int = 1):
        """Chuẩn bị stream phát liên tục."""
        self._ensure_output_stream(sample_rate, channels)

    def stop_stream(self):
        """Dừng stream phát liên tục."""
        with self._stream_lock:
            if self._out_stream is not None:
                try:
                    self._out_stream.stop()
                    self._out_stream.close()
                except Exception:
                    pass
                self._out_stream = None
                self._stream_rate = None
                self._stream_channels = None
                self._stream_blocksize = None
            # Xoá hàng đợi
            while not self._out_queue.empty():
                try:
                    self._out_queue.get_nowait()
                except Exception:
                    break
            logger.info("🔇 OutputStream stopped")

    def play_stream_frame(self, audio_array: np.ndarray, sample_rate: int, channels: int):
        """Đưa một frame audio vào hàng đợi để phát liên tục."""
        try:
            # Chuẩn hoá shape: (samples, channels)
            if audio_array.ndim == 1:
                audio_array = audio_array.reshape(-1, 1)
            elif audio_array.ndim == 2:
                # Nhiều trường hợp audio từ PyAV là (channels, samples)
                if audio_array.shape[0] in (1, 2) and audio_array.shape[0] <= audio_array.shape[1]:
                    # (ch, samples) -> (samples, ch)
                    audio_array = audio_array.T
            # Bảo toàn số kênh mong muốn
            if channels == 1 and audio_array.shape[1] == 2:
                audio_array = audio_array[:, 0:1]
            elif channels == 2 and audio_array.shape[1] == 1:
                audio_array = np.repeat(audio_array, 2, axis=1)

            target_rate = sample_rate  # Giữ nguyên theo nguồn để tránh resample nhiều lần
            # Convert dtype -> float32 [-1,1]
            if audio_array.dtype == np.int16:
                audio_array = audio_array.astype(np.float32) / 32767.0
            elif audio_array.dtype == np.int32:
                audio_array = audio_array.astype(np.float32) / 2147483647.0
            elif audio_array.dtype != np.float32:
                audio_array = audio_array.astype(np.float32)

            # Đảm bảo stream mở đúng tham số
            self._ensure_output_stream(target_rate, channels)

            # Đưa vào hàng đợi, nếu đầy thì bỏ bớt để không lag
            try:
                self._out_queue.put_nowait(audio_array)
            except queue.Full:
                try:
                    _ = self._out_queue.get_nowait()
                except Exception:
                    pass
                try:
                    self._out_queue.put_nowait(audio_array)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"❌ Lỗi enqueue frame phát audio: {e}", exc_info=True)