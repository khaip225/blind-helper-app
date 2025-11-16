"""
Xử lý audio
"""
import asyncio
import platform
import fractions
import queue
import os
import sys
import numpy as np
import av
from aiortc.mediastreams import MediaStreamTrack
from aiortc.contrib.media import MediaPlayer, MediaRecorder
from config import (
    logger, state, DEVICE_ID,
    PLAYBACK_GAIN, PLAYBACK_OUTPUT_RATE,
    MICROPHONE_GAIN, MICROPHONE_NOISE_GATE,
    PLAYBACK_AUTO_GAIN, PLAYBACK_TARGET_RMS, PLAYBACK_MAX_GAIN,
    PLAYBACK_MAX_GAIN_TOTAL, PLAYBACK_COMPRESSOR_ENABLED, PLAYBACK_COMPRESSOR_DRIVE
)

class SuppressALSAErrors:
    """Context manager to suppress ALSA error messages"""
    def __enter__(self):
        # Redirect stderr to devnull to suppress ALSA warnings
        self.stderr = sys.stderr
        try:
            sys.stderr = open(os.devnull, 'w')
        except Exception:
            pass
        return self
    
    def __exit__(self, *args):
        # Restore stderr
        try:
            sys.stderr.close()
        except Exception:
            pass
        sys.stderr = self.stderr

class PyAudioSourceTrack(MediaStreamTrack):
    """Audio track sử dụng PyAudio"""
    kind = "audio"

    def __init__(self, rate=48000, channels=1, frames_per_buffer=960, device_index=None, gain=2.0):
        super().__init__()
        self._rate = rate
        self._channels = channels
        self._chunk = frames_per_buffer
        self._time_base = fractions.Fraction(1, rate)
        self._pts = 0
        self._gain = gain
        self._queue = queue.Queue(maxsize=100)
        self._frame_count = 0

        try:
            import pyaudio
            self._pa = pyaudio.PyAudio()
            
            # USB mics typically support 48000 or 44100
            supported_rates = [48000, 44100]
            selected_rate = rate
            
            if device_index is not None:
                # Test requested rate first
                rate_supported = False
                try:
                    if self._pa.is_format_supported(
                        rate,
                        input_device=device_index,
                        input_channels=channels,
                        input_format=pyaudio.paInt16
                    ):
                        rate_supported = True
                except Exception:
                    pass
                
                # If not supported, try alternatives
                if not rate_supported:
                    for test_rate in supported_rates:
                        if test_rate == rate:
                            continue
                        try:
                            if self._pa.is_format_supported(
                                test_rate,
                                input_device=device_index,
                                input_channels=channels,
                                input_format=pyaudio.paInt16
                            ):
                                selected_rate = test_rate
                                logger.info(f"⚠️ Rate {rate} not supported, using {selected_rate}")
                                self._rate = selected_rate
                                break
                        except Exception:
                            continue
            
            stream_kwargs = {
                'format': pyaudio.paInt16,
                'channels': self._channels,
                'rate': self._rate,
                'input': True,
                'frames_per_buffer': self._chunk,
                'stream_callback': self._on_audio,
            }
            
            if device_index is not None:
                stream_kwargs['input_device_index'] = device_index
            
            self._stream = self._pa.open(**stream_kwargs)
            self._stream.start_stream()
            
            device_info = " (default)" if device_index is None else f" (device {device_index})"
            logger.info(f"🎤 Using PyAudio microphone{device_info} with gain={self._gain}x, rate={self._rate}")
        except Exception as e:
            logger.error(f"Failed to initialize PyAudio: {e}")
            raise

    def _on_audio(self, in_data, frame_count, time_info, status_flags):
        try:
            self._queue.put_nowait(in_data)
        except queue.Full:
            # Drop oldest to make room
            try:
                _ = self._queue.get_nowait()
            except Exception:
                pass
            try:
                self._queue.put_nowait(in_data)
            except Exception:
                pass
        return (None, 0)

    async def recv(self):
        # Wait for next chunk of audio from the callback
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, self._queue.get)
        
        self._frame_count += 1
        
        # Apply gain and noise gate
        if self._gain != 1.0:
            # Convert to numpy for processing
            samples = np.frombuffer(data, dtype=np.int16).copy()
            
            # Log audio levels every 100 frames (~2 seconds at 48kHz/960 buffer)
            if self._frame_count % 100 == 1:
                rms_before = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
                max_before = np.max(np.abs(samples))
                logger.info(f"🎤 Audio levels BEFORE gain: RMS={rms_before:.0f}, Max={max_before}, Gain={self._gain}x")
            
            # Apply gain
            samples = samples.astype(np.float32) * self._gain
            
            # Noise gate: suppress very quiet signals (reduce hiss/noise)
            noise_threshold = MICROPHONE_NOISE_GATE
            samples[np.abs(samples) < noise_threshold] = 0
            
            # Log audio levels after gain
            if self._frame_count % 100 == 1:
                rms_after = np.sqrt(np.mean(samples ** 2))
                max_after = np.max(np.abs(samples))
                logger.info(f"🔊 Audio levels AFTER gain: RMS={rms_after:.0f}, Max={max_after:.0f}, NoiseGate={noise_threshold}")
            
            # Clip to prevent distortion
            samples = np.clip(samples, -32768, 32767).astype(np.int16)
            data = samples.tobytes()
        
        # Create an AudioFrame from raw int16 PCM
        frame = av.AudioFrame(
            format="s16",
            layout="mono" if self._channels == 1 else "stereo",
            samples=self._chunk,
        )
        frame.pts = self._pts
        frame.sample_rate = self._rate
        frame.time_base = self._time_base
        # Update plane with raw bytes
        frame.planes[0].update(data)
        self._pts += self._chunk
        return frame

    def stop(self):
        try:
            if hasattr(self, "_stream") and self._stream:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        try:
            if hasattr(self, "_pa") and self._pa:
                self._pa.terminate()
        except Exception:
            pass
        super().stop()

def setup_audio_player():
    """Thiết lập audio player theo platform"""
    if platform.system() == "Windows":
        # Try PyAudio first
        try:
            pyaudio_track = PyAudioSourceTrack(rate=48000, channels=1, frames_per_buffer=960, gain=1.0)
            return None, pyaudio_track
        except Exception:
            logger.warning("PyAudio not available, trying DirectShow...")
        
        # Fallback to DirectShow
        audio_options = {"channels": "1", "sample_rate": "48000"}
        for idx in range(5):
            try:
                audio_player = MediaPlayer(
                    f"audio=@device_cm_{{{idx}}}",
                    format="dshow",
                    options=audio_options,
                )
                logger.info(f"🎤 Using DirectShow microphone device index: {idx}")
                return audio_player, None
            except Exception:
                continue
        
        # Try by name
        audio_devices = ["Microphone Array", "Microphone", "Realtek Audio"]
        for audio_name in audio_devices:
            try:
                audio_player = MediaPlayer(
                    f"audio={audio_name}",
                    format="dshow",
                    options=audio_options,
                )
                logger.info(f"🎤 Using DirectShow microphone: {audio_name}")
                return audio_player, None
            except Exception:
                continue
        
        logger.warning("Could not open any microphone device")
        return None, None
    
    elif platform.system() == "Linux":
        # 🎤 Jetson Nano: Use PyAudio directly (bypasses FFmpeg ALSA config issues)
        # Try to find USB Audio Device (card 3) for microphone
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            
            # Find USB Audio Device with input channels
            mic_device_index = None
            with SuppressALSAErrors():
                try:
                    info = pa.get_host_api_info_by_index(0)
                    numdevices = info.get('deviceCount', 0)
                    for i in range(numdevices):
                        try:
                            device_info = pa.get_device_info_by_host_api_device_index(0, i)
                            name = device_info.get('name', '')
                            max_in = device_info.get('maxInputChannels', 0)
                            
                            # Look for USB Audio Device or hw:3,0 with input
                            if (max_in > 0 and 
                                ('USB Audio Device' in name or 'hw:3,0' in name)):
                                mic_device_index = i
                                logger.info(f"🎤 Found USB mic device: {name} (index={i})")
                                break
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning(f"Could not enumerate audio devices: {e}")
            
            pa.terminate()
            
            # Use PyAudio with found device
            if mic_device_index is not None:
                pyaudio_track = PyAudioSourceTrack(
                    rate=48000, 
                    channels=1, 
                    frames_per_buffer=960,
                    device_index=mic_device_index,
                    gain=1.0
                )
                return None, pyaudio_track
            else:
                # Fallback to default device
                logger.info("🎤 Using default PyAudio microphone")
                pyaudio_track = PyAudioSourceTrack(
                    rate=48000, 
                    channels=1, 
                    frames_per_buffer=960,
                    gain=1.0
                )
                return None, pyaudio_track
                
        except Exception as e:
            logger.warning(f"PyAudio not available: {e}")
            return None, None
    
    return None, None

async def play_incoming_audio(track):
    """Phát audio nhận được từ remote"""
    try:
        import pyaudio
    except ImportError:
        logger.warning("PyAudio not installed - skipping local audio playback")
        return

    if state._pyaudio_out is None:
        # Suppress ALSA errors when initializing PyAudio
        with SuppressALSAErrors():
            state._pyaudio_out = pyaudio.PyAudio()

    current_cfg = (None, None)  # (rate, channels)
    resampler = None
    resample_cfg = (None, None)  # (rate, channels)
    
    # 🔊 Jetson Nano: Try to find USB Audio Device (card 3) for playback
    # Card 3 is both microphone and speaker (USB Audio Device)
    output_device_index = None
    if platform.system() == "Linux":
        # Suppress ALSA errors when enumerating devices
        with SuppressALSAErrors():
            try:
                info = state._pyaudio_out.get_host_api_info_by_index(0)
                numdevices = info.get('deviceCount', 0)
                for i in range(numdevices):
                    try:
                        device_info = state._pyaudio_out.get_device_info_by_host_api_device_index(0, i)
                        name = device_info.get('name', '')
                        max_out = device_info.get('maxOutputChannels', 0)
                        
                        # Look for USB Audio Device or hw:3,0
                        if (max_out > 0 and 
                            ('USB Audio Device' in name or 'hw:3,0' in name)):
                            output_device_index = i
                            logger.info(f"🔊 Found USB speaker device: {name} (index={i})")
                            break
                    except Exception:
                        # Silently skip problematic devices (virtual/surround devices)
                        continue
            except Exception as e:
                logger.warning(f"Could not enumerate audio devices: {e}")
    
    try:
        while True:
            frame = await track.recv()
            # Determine desired output channels (1 or 2)
            in_channels = 1
            try:
                if getattr(frame, "layout", None) is not None:
                    in_channels = getattr(frame.layout, "channels", 1) or 1
                else:
                    probe = frame.to_ndarray()
                    in_channels = 1 if probe.ndim == 1 else min(probe.shape[0], 2)
            except Exception:
                in_channels = 1
            out_channels = 1 if in_channels == 1 else 2

            # (Re)create resampler if config changed
            if resampler is None or resample_cfg != (PLAYBACK_OUTPUT_RATE, out_channels):
                layout = "mono" if out_channels == 1 else "stereo"
                try:
                    resampler = av.audio.resampler.AudioResampler(
                        format="s16", layout=layout, rate=PLAYBACK_OUTPUT_RATE
                    )
                    resample_cfg = (PLAYBACK_OUTPUT_RATE, out_channels)
                    logger.info(f"🎛️ Resampler configured -> rate={PLAYBACK_OUTPUT_RATE}, channels={out_channels}")
                except Exception as e:
                    logger.warning(f"Failed to create resampler, using raw frames: {e}")
                    resampler = None

            try:
                if resampler is not None:
                    out_frames = resampler.resample(frame)
                    chunks = []
                    for rf in out_frames:
                        arr = rf.to_ndarray()
                        if arr.dtype != np.int16:
                            arr = arr.astype(np.int16, copy=False)
                        if arr.ndim == 1:
                            ch = 1
                            pcm_arr = arr
                        else:
                            ch = arr.shape[0]
                            if ch == 1:
                                pcm_arr = arr[0]
                            else:
                                pcm_arr = arr.T.reshape(-1)
                        chunks.append(pcm_arr)
                    pcm = np.concatenate(chunks) if chunks else np.empty(0, dtype=np.int16)
                    rate = PLAYBACK_OUTPUT_RATE
                    channels = out_channels
                else:
                    # Fallback to original frame properties
                    rate = getattr(frame, "sample_rate", PLAYBACK_OUTPUT_RATE) or PLAYBACK_OUTPUT_RATE
                    arr = frame.to_ndarray()
                    if arr.dtype == np.float32 or arr.dtype == np.float64:
                        arr = np.clip(arr, -1.0, 1.0)
                        arr = (arr * 32767.0).astype(np.int16)
                    elif arr.dtype == np.int32:
                        arr = (arr >> 16).astype(np.int16)
                    elif arr.dtype != np.int16:
                        arr = arr.astype(np.int16, copy=False)
                    if arr.ndim == 1:
                        channels = 1
                        pcm = arr
                    else:
                        channels = arr.shape[0]
                        if channels > 2:
                            arr = np.mean(arr, axis=0).astype(np.int16)
                            channels = 1
                            pcm = arr
                        elif channels == 1:
                            pcm = arr[0]
                        else:
                            pcm = arr.T.reshape(-1)
            except Exception as e:
                logger.warning(f"Resample/convert error: {e}")
                await asyncio.sleep(0.01)
                continue

            # Apply gain: base gain + optional auto gain control (AGC), sau đó nén mềm (soft limiter)
            applied_gain = float(PLAYBACK_GAIN)  # base gain
            if PLAYBACK_AUTO_GAIN:
                # Tính RMS và scale về mức mục tiêu, giới hạn hệ số
                # Tránh boost khi gần như im lặng
                rms = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2)) + 1e-6)
                if rms > 200.0:  # ngưỡng im lặng
                    agc_gain = float(PLAYBACK_TARGET_RMS) / rms
                    if agc_gain < 1.0:
                        # chỉ boost khi nhỏ, tránh hạ volume đột ngột
                        agc_gain = 1.0
                    agc_gain = min(agc_gain, float(PLAYBACK_MAX_GAIN))
                    applied_gain = min(applied_gain * agc_gain, float(PLAYBACK_MAX_GAIN_TOTAL))
            if applied_gain != 1.0 or PLAYBACK_COMPRESSOR_ENABLED:
                # Chuẩn hóa về float32 [-1, 1]
                x = pcm.astype(np.float32) / 32768.0
                # Preamp
                if applied_gain != 1.0:
                    x = x * applied_gain
                # Soft limiter / compressor bằng tanh
                if PLAYBACK_COMPRESSOR_ENABLED:
                    drive = float(PLAYBACK_COMPRESSOR_DRIVE)
                    if drive > 0.0:
                        # Chuẩn hóa tránh giảm tổng mức: tanh(d*x)/tanh(d)
                        x = np.tanh(drive * x) / np.tanh(drive)
                # Clip an toàn và chuyển về int16
                x = np.clip(x, -1.0, 1.0)
                amplified = (x * 32767.0).astype(np.int16)
                pcm_bytes = amplified.tobytes()
            else:
                pcm_bytes = pcm.tobytes()

            if current_cfg != (rate, channels) or state._pyaudio_out_stream is None:
                # (Re)open output stream with new format
                try:
                    if state._pyaudio_out_stream is not None:
                        state._pyaudio_out_stream.stop_stream()
                        state._pyaudio_out_stream.close()
                except Exception:
                    pass
                
                # 🔊 Open stream with USB Audio Device if found
                stream_kwargs = {
                    'format': pyaudio.paInt16,
                    'channels': channels,
                    'rate': rate,
                    'output': True,
                    'frames_per_buffer': 960,
                }
                if output_device_index is not None:
                    stream_kwargs['output_device_index'] = output_device_index
                
                state._pyaudio_out_stream = state._pyaudio_out.open(**stream_kwargs)
                logger.info(f"🔊 Audio playback started (rate={rate}, channels={channels}, device={output_device_index})")
                current_cfg = (rate, channels)

            try:
                state._pyaudio_out_stream.write(pcm_bytes)
                # Debug: Log every 100 frames
                if not hasattr(state, '_audio_frame_count'):
                    state._audio_frame_count = 0
                state._audio_frame_count += 1
                if state._audio_frame_count % 100 == 0:
                    logger.info(f"🔊 Audio frames written: {state._audio_frame_count}, bytes: {len(pcm_bytes)}")
            except Exception as werr:
                logger.warning(f"Audio playback write issue: {werr}")
                await asyncio.sleep(0.01)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        if str(e).strip() == "":
            logger.info("🔇 Audio playback ended (track finished)")
        else:
            logger.warning(f"Audio playback stopped due to error: {e}")

async def handle_incoming_audio_track(track):
    """Xử lý incoming audio track"""
    try:
        logger.info(f"📥 Incoming audio track: id={track.id}")
        
        # Record incoming audio to file
        try:
            state.recorder = MediaRecorder(f"received_{DEVICE_ID}_audio.wav")
            await state.recorder.start()
            state.recorder.addTrack(track)
            logger.info(f"🎧 Recording incoming audio to received_{DEVICE_ID}_audio.wav")
        except Exception as e:
            logger.warning(f"Could not start recorder for incoming audio: {e}")

        # Start local playback
        if state.playback_task is None or state.playback_task.done():
            state.playback_task = asyncio.create_task(play_incoming_audio(track))
            logger.info("🔈 Local audio playback task started")
    except Exception as e:
        logger.error(f"Error handling incoming audio track: {e}")