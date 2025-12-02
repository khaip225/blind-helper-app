"""
Message Handlers
================
"""

import base64
import json
import os
import sys
import platform
import numpy as np
import time
import threading
import soundfile as sf
import asyncio
import av
import sounddevice as sd
from config import BASE_DIR, DEVICE_ID
from module.voice_speaker import VoiceSpeaker
from .gprs_connection import GPRSConnection
from container import container

from log import setup_logger
logger = setup_logger(__name__)


from .webrtc_manager import WebRTCManager


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

   
audio_stream_buffers = {}
# Thời gian tối đa (giây) để chờ đợi tất cả các chunks
STREAM_TIMEOUT = 15  # Tăng thời gian timeout lên 15 giây
class MessageHandler:
    """Handle incoming MQTT messages"""

    def __init__(self, mqtt_client=None):
        self.speaker = VoiceSpeaker("USB Audio Device")
        self.gprs = GPRSConnection()
        self._gprs_ready = False
        self.mqtt_client = mqtt_client
        
        # WebRTC Manager
        self.webrtc = WebRTCManager(DEVICE_ID, mqtt_client)
        # Setup callbacks
        self.webrtc.on_audio_track = self._handle_incoming_audio
        self.webrtc.on_connection_state_change = self._on_webrtc_state_change
        
        # Khởi động event loop cho WebRTC
        self.webrtc.start_event_loop()
        
        # VoiceMQTT reference (sẽ được set từ bên ngoài)
        self.voice_mqtt = None
        
        # PyAudio state for WebRTC playback (tương tự audio_handler.py)
        self._pyaudio_out = None
        self._pyaudio_out_stream = None
        self._audio_frame_count = 0
        
        # Playback config (có thể lấy từ config.py nếu có)
        self.PLAYBACK_OUTPUT_RATE = 48000  # Default 48kHz cho WebRTC
        self.PLAYBACK_GAIN = 0.3  # ✅ Giảm xuống 30% để tránh clipping từ phone mic
        self.PLAYBACK_AUTO_GAIN = False
        self.PLAYBACK_TARGET_RMS = 5000.0
        self.PLAYBACK_MAX_GAIN = 2.0
        self.PLAYBACK_MAX_GAIN_TOTAL = 3.0
        self.PLAYBACK_COMPRESSOR_ENABLED = False
        self.PLAYBACK_COMPRESSOR_DRIVE = 2.0
        
        # Khởi tạo luồng kiểm tra timeout cho audio streams
        self.cleanup_thread = threading.Thread(target=self._cleanup_old_streams, daemon=True)
        self.cleanup_thread.start()
    
    def set_voice_mqtt(self, voice_mqtt):
        """Set VoiceMQTT instance để có thể pause/resume khi có cuộc gọi"""
        self.voice_mqtt = voice_mqtt
        logger.info("✅ VoiceMQTT linked to MessageHandler")
    
    async def initiate_sos_call(self):
        """Initiate SOS emergency call from device to mobile"""
        logger.info("🆘 Initiating SOS call...")
        
        # Pause VAD before starting call
        if self.voice_mqtt:
            try:
                self.voice_mqtt.pause_vad()
                logger.info("⏸️ VAD paused for SOS call")
                
                # ✅ Đợi một chút để đảm bảo sounddevice đã close stream
                await asyncio.sleep(0.5)  # 500ms để device được release
                logger.info("✅ Device should be released now")
            except Exception as e:
                logger.error(f"Error pausing VAD: {e}")
        
        # Call WebRTC manager's initiate_sos_call
        return await self.webrtc.initiate_sos_call()


    def handle_message(self, topic: str, payload: dict):
        """Route messages to appropriate handlers"""
        if not topic.endswith("/audio"):
            logger.info(f"Handling {topic}")

        if topic.endswith("/audio"):
            self.handle_stt_audio(payload)
        elif topic.endswith("/command"):
            self.handle_command(payload)
        elif topic.endswith("webrtc/offer"):
            self.handle_webrtc_offer(payload)
        elif topic.endswith("webrtc/candidate"):
            self.handle_webrtc_candidate(payload)
        elif topic.endswith("webrtc/answer"):
            self.handle_webrtc_answer(payload)
        else:
            logger.warning(f"No handler for {topic}")
    
    def handle_webrtc_offer(self, payload):
        """Xử lý WebRTC offer từ mobile"""
        if not self.webrtc:
            logger.error("❌ WebRTC Manager not initialized")
            return
        
        try:
            sdp = payload.get("sdp")
            offer_type = payload.get("type", "offer")
            
            if not sdp:
                logger.error("❌ No SDP in offer payload")
                return
            
            logger.info("📞 Handling WebRTC offer from mobile")
            
            # Chạy trong thread riêng để không block MQTT
            thread = threading.Thread(
                target=self._run_async_offer_handler,
                args=(sdp, offer_type),
                daemon=True
            )
            thread.start()
            
        except Exception as e:
            logger.error(f"❌ Error handling WebRTC offer: {e}", exc_info=True)
    
    def _run_async_offer_handler(self, sdp: str, offer_type: str):
        """Chạy async handler trong event loop riêng"""
        try:
            # ⚠️ CRITICAL: Pause VAD TRƯỚC KHI mở WebRTC mic
            if self.voice_mqtt:
                try:
                    self.voice_mqtt.pause_vad()
                    logger.info("⏸️ VAD paused BEFORE WebRTC initialization")
                    
                    # ✅ Đợi một chút để đảm bảo sounddevice đã close stream
                    time.sleep(0.5)  # 500ms để device được release
                    logger.info("✅ Device should be released now")
                except Exception as e:
                    logger.error(f"Error pausing VAD: {e}")
            
            # Sử dụng event loop riêng của WebRTC Manager
            future = self.webrtc.run_async(self.webrtc.handle_offer(sdp, offer_type))
            
            # Đợi kết quả (với timeout để tránh block vĩnh viễn)
            if future:
                try:
                    future.result(timeout=30)  # Timeout 30 giây
                except Exception as e:
                    logger.error(f"❌ Error waiting for offer handler: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Error in async offer handler: {e}", exc_info=True)

    
    def handle_webrtc_candidate(self, payload):
        """Xử lý ICE candidate từ mobile"""
        if not self.webrtc:
            logger.debug("WebRTC Manager not initialized, skipping candidate")
            return
        
        try:
            # Chạy async trong thread riêng
            thread = threading.Thread(
                target=self._run_async_candidate_handler,
                args=(payload,),
                daemon=True
            )
            thread.start()
            
        except Exception as e:
            logger.error(f"❌ Error handling ICE candidate: {e}")
    
    def _run_async_candidate_handler(self, candidate_data: dict):
        """Chạy async candidate handler"""
        try:
            # Sử dụng event loop riêng của WebRTC Manager
            future = self.webrtc.run_async(self.webrtc.handle_ice_candidate(candidate_data))
            
            # Đợi kết quả (với timeout ngắn)
            if future:
                try:
                    future.result(timeout=5)  # Timeout 5 giây
                except Exception as e:
                    logger.error(f"❌ Error waiting for candidate handler: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Error in async candidate handler: {e}", exc_info=True)
    
    def handle_webrtc_answer(self, payload):
        """Xử lý WebRTC answer từ mobile khi device initiate call"""
        if not self.webrtc:
            logger.error("❌ WebRTC Manager not initialized")
            return
        
        try:
            sdp = payload.get("sdp")
            answer_type = payload.get("type", "answer")
            
            if not sdp:
                logger.error("❌ No SDP in answer payload")
                return
            
            logger.info("📥 Handling WebRTC answer from mobile")
            
            # Chạy trong thread riêng để không block MQTT
            thread = threading.Thread(
                target=self._run_async_answer_handler,
                args=(sdp, answer_type),
                daemon=True
            )
            thread.start()
            
        except Exception as e:
            logger.error(f"❌ Error handling WebRTC answer: {e}", exc_info=True)
    
    def _run_async_answer_handler(self, sdp: str, answer_type: str):
        """Chạy async answer handler trong event loop riêng"""
        try:
            # Sử dụng event loop riêng của WebRTC Manager
            future = self.webrtc.run_async(self.webrtc.handle_answer(sdp, answer_type))
            
            # Đợi kết quả (với timeout để tránh block vĩnh viễn)
            if future:
                try:
                    future.result(timeout=30)  # Timeout 30 giây
                except Exception as e:
                    logger.error(f"❌ Error waiting for answer handler: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Error in async answer handler: {e}", exc_info=True)
    
    async def _handle_incoming_audio(self, track):
        """Callback khi nhận audio track từ mobile - phát ra loa sử dụng PyAudio (tương tự audio_handler.py)"""
        try:
            logger.info(f"🎧 Receiving audio from mobile: {track.id}")
            
            # Import PyAudio
            try:
                import pyaudio
            except ImportError:
                logger.warning("PyAudio not installed - falling back to VoiceSpeaker")
                await self._handle_incoming_audio_fallback(track)
                return

            # Initialize PyAudio nếu chưa có
            if self._pyaudio_out is None:
                with SuppressALSAErrors():
                    self._pyaudio_out = pyaudio.PyAudio()

            current_cfg = (None, None)  # (rate, channels)
            resampler = None
            resample_cfg = (None, None)  # (rate, channels)
            
            # 🔊 Jetson Nano: Tìm USB Audio Device (card 3) cho playback
            output_device_index = None
            if platform.system() == "Linux":
                with SuppressALSAErrors():
                    try:
                        info = self._pyaudio_out.get_host_api_info_by_index(0)
                        numdevices = info.get('deviceCount', 0)
                        for i in range(numdevices):
                            try:
                                device_info = self._pyaudio_out.get_device_info_by_host_api_device_index(0, i)
                                name = device_info.get('name', '')
                                max_out = device_info.get('maxOutputChannels', 0)
                                
                                # Tìm USB Audio Device hoặc hw:3,0
                                if (max_out > 0 and 
                                    ('USB Audio Device' in name or 'hw:3,0' in name)):
                                    output_device_index = i
                                    logger.info(f"🔊 Found USB speaker device: {name} (index={i})")
                                    break
                            except Exception:
                                # Bỏ qua các device có vấn đề
                                continue
                    except Exception as e:
                        logger.warning(f"Could not enumerate audio devices: {e}")
            
            try:
                while True:
                    frame = await track.recv()
                    
                    # ✅ FORCE MONO để tránh channel doubling (1 -> 2 sẽ làm tăng volume gấp đôi)
                    in_channels = 1
                    try:
                        if getattr(frame, "layout", None) is not None:
                            in_channels = getattr(frame.layout, "channels", 1) or 1
                        else:
                            probe = frame.to_ndarray()
                            in_channels = 1 if probe.ndim == 1 else min(probe.shape[0], 2)
                    except Exception:
                        in_channels = 1
                    out_channels = 1  # ✅ FORCE MONO thay vì: 1 if in_channels == 1 else 2

                    # Tạo resampler nếu config thay đổi
                    if resampler is None or resample_cfg != (self.PLAYBACK_OUTPUT_RATE, out_channels):
                        layout = "mono" if out_channels == 1 else "stereo"
                        try:
                            resampler = av.audio.resampler.AudioResampler(
                                format="s16", layout=layout, rate=self.PLAYBACK_OUTPUT_RATE
                            )
                            resample_cfg = (self.PLAYBACK_OUTPUT_RATE, out_channels)
                            logger.info(f"🎛️ Resampler configured -> rate={self.PLAYBACK_OUTPUT_RATE}, channels={out_channels}")
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
                            rate = self.PLAYBACK_OUTPUT_RATE
                            channels = out_channels
                        else:
                            # Fallback: dùng thuộc tính frame gốc
                            rate = getattr(frame, "sample_rate", self.PLAYBACK_OUTPUT_RATE) or self.PLAYBACK_OUTPUT_RATE
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

                    # Áp dụng gain: base gain + optional auto gain control (AGC), sau đó soft limiter
                    applied_gain = float(self.PLAYBACK_GAIN)
                    if self.PLAYBACK_AUTO_GAIN:
                        rms = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2)) + 1e-6)
                        if rms > 200.0:  # ngưỡng im lặng
                            agc_gain = float(self.PLAYBACK_TARGET_RMS) / rms
                            if agc_gain < 1.0:
                                agc_gain = 1.0
                            agc_gain = min(agc_gain, float(self.PLAYBACK_MAX_GAIN))
                            applied_gain = min(applied_gain * agc_gain, float(self.PLAYBACK_MAX_GAIN_TOTAL))
                    
                    if applied_gain != 1.0 or self.PLAYBACK_COMPRESSOR_ENABLED:
                        # Chuẩn hóa về float32 [-1, 1]
                        x = pcm.astype(np.float32) / 32768.0
                        # Preamp
                        if applied_gain != 1.0:
                            x = x * applied_gain
                        # Soft limiter / compressor bằng tanh
                        if self.PLAYBACK_COMPRESSOR_ENABLED:
                            drive = float(self.PLAYBACK_COMPRESSOR_DRIVE)
                            if drive > 0.0:
                                x = np.tanh(drive * x) / np.tanh(drive)
                        # Clip an toàn và chuyển về int16
                        x = np.clip(x, -1.0, 1.0)
                        amplified = (x * 32767.0).astype(np.int16)
                        pcm_bytes = amplified.tobytes()
                    else:
                        pcm_bytes = pcm.tobytes()

                    # Mở lại stream nếu config thay đổi
                    if current_cfg != (rate, channels) or self._pyaudio_out_stream is None:
                        try:
                            if self._pyaudio_out_stream is not None:
                                self._pyaudio_out_stream.stop_stream()
                                self._pyaudio_out_stream.close()
                        except Exception:
                            pass
                        
                        # 🔊 Mở stream với USB Audio Device nếu tìm thấy
                        stream_kwargs = {
                            'format': pyaudio.paInt16,
                            'channels': channels,
                            'rate': rate,
                            'output': True,
                            'frames_per_buffer': 960,
                        }
                        if output_device_index is not None:
                            stream_kwargs['output_device_index'] = output_device_index
                        
                        self._pyaudio_out_stream = self._pyaudio_out.open(**stream_kwargs)
                        logger.info(f"🔊 Audio playback started (rate={rate}, channels={channels}, device={output_device_index})")
                        current_cfg = (rate, channels)

                    try:
                        self._pyaudio_out_stream.write(pcm_bytes)
                        # Debug: Log mỗi 100 frames
                        self._audio_frame_count += 1
                        if self._audio_frame_count % 100 == 0:
                            logger.info(f"🔊 Audio frames written: {self._audio_frame_count}, bytes: {len(pcm_bytes)}")
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
            finally:
                # Cleanup stream
                try:
                    if self._pyaudio_out_stream is not None:
                        self._pyaudio_out_stream.stop_stream()
                        self._pyaudio_out_stream.close()
                        self._pyaudio_out_stream = None
                except Exception:
                    pass
                logger.info("🔊 Audio playback finished")
                    
        except Exception as e:
            logger.error(f"❌ Error handling incoming audio: {e}", exc_info=True)
    
    async def _handle_incoming_audio_fallback(self, track):
        """Fallback sử dụng VoiceSpeaker nếu PyAudio không có"""
        try:
            logger.info(f"🎧 Using VoiceSpeaker fallback for audio playback")
            speaker = container.get("speaker")
            started = False
            
            while True:
                try:
                    frame: av.AudioFrame = await track.recv()
                    sample_rate = frame.sample_rate
                    frame_channels = len(frame.layout.channels)
                    
                    audio_array = frame.to_ndarray()
                    if audio_array.ndim == 1:
                        audio_array = audio_array.reshape(-1, 1)
                    elif audio_array.ndim == 2 and audio_array.shape[0] in (1, 2) and audio_array.shape[0] <= audio_array.shape[1]:
                        audio_array = audio_array.T
                    
                    if not started:
                        speaker.start_stream(sample_rate=sample_rate, channels=min(2, frame_channels))
                        started = True
                    speaker.play_stream_frame(audio_array, sample_rate=sample_rate, channels=min(2, frame_channels))
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"❌ Error in fallback playback: {e}", exc_info=True)
                    break
        except Exception as e:
            logger.error(f"❌ Error in fallback audio handler: {e}", exc_info=True)
        finally:
            try:
                speaker.stop_stream()
            except Exception:
                pass
    
    def _on_webrtc_state_change(self, state: str):
        """Callback khi trạng thái WebRTC thay đổi"""
        logger.info(f"🔄 WebRTC state changed to: {state}")
        
        if state == "connected":
            logger.info("🎉 WebRTC connection established successfully!")
            # VAD đã được pause trước khi initialize rồi, không cần pause lại
                    
        elif state == "failed":
            logger.error("❌ WebRTC connection failed")
            # Resume VAD khi cuộc gọi failed
            if self.voice_mqtt:
                try:
                    self.voice_mqtt.resume_vad()
                    logger.info("▶️ VAD resumed after WebRTC failed")
                except Exception as e:
                    logger.error(f"Error resuming VAD: {e}")
                    
        elif state == "disconnected":
            logger.warning("⚠️ WebRTC connection disconnected")
            # Resume VAD khi cuộc gọi disconnected
            if self.voice_mqtt:
                try:
                    self.voice_mqtt.resume_vad()
                    logger.info("▶️ VAD resumed after WebRTC disconnected")
                except Exception as e:
                    logger.error(f"Error resuming VAD: {e}")
                    
        elif state == "closed":
            logger.info("🔒 WebRTC connection closed")
            # Resume VAD khi cuộc gọi closed
            if self.voice_mqtt:
                try:
                    self.voice_mqtt.resume_vad()
                    logger.info("▶️ VAD resumed after WebRTC closed")
                except Exception as e:
                    logger.error(f"Error resuming VAD: {e}") 
    
    def handle_stt_audio(self, payload):
        """
        Xử lý luồng âm thanh từ thiết bị và chuyển đổi thành văn bản khi nhận đủ
        """
        try:
            stream_id = payload.get("serverStreamId")
            chunk_index = payload.get("chunkIndex", 0)
            total_chunks = payload.get("totalChunks", 1)
            is_last = payload.get("isLast", False)
            format_audio = payload.get("format", "pcm16le")
            sample_rate = payload.get("sampleRate", 44100)
            
            # Kiểm tra dữ liệu âm thanh
            data_str = payload.get("data", "")
            if not data_str:
                logger.error(f"Empty audio data for chunk {chunk_index}")
                return
                
            logger.debug(f"Received audio chunk {chunk_index} with sample rate {sample_rate} from server (stream: {stream_id})")
            
            # Giải mã âm thanh từ base64 an toàn
            try:
                audio_chunk = base64.b64decode(data_str)
            except Exception as e:
                logger.error(f"Error decoding base64 data: {e}")
                return

            
            # Tạo key duy nhất cho stream này
            stream_key = f"{stream_id}"
            
            # Khởi tạo buffer cho stream nếu chưa tồn tại
            if stream_key not in audio_stream_buffers:
                audio_stream_buffers[stream_key] = {
                    "chunks": {},
                    "total_chunks": total_chunks,
                    "received_chunks": 0,
                    "format": format_audio,
                    "sample_rate": sample_rate,
                    "timestamp": time.time()
                }
            
            # Lưu chunk vào buffer
            audio_stream_buffers[stream_key]["chunks"][chunk_index] = audio_chunk
            audio_stream_buffers[stream_key]["received_chunks"] += 1
            
            logger.debug(f"Received audio chunk {chunk_index+1}/{total_chunks} from server (stream: {stream_id})")
            
            # Kiểm tra xem đã nhận đủ chunks chưa hoặc đã nhận chunk cuối cùng
            if is_last or audio_stream_buffers[stream_key]["received_chunks"] >= total_chunks:
                # Xử lý ngay cả khi chưa nhận đủ tất cả các chunks
                logger.info(f"Completed audio stream {stream_id} from server, processing...")
                
                # Kết hợp các chunks theo thứ tự
                all_chunks = []
                for i in range(total_chunks):
                    if i in audio_stream_buffers[stream_key]["chunks"]:
                        all_chunks.append(audio_stream_buffers[stream_key]["chunks"][i])
                    else:
                        logger.warning(f"Missing chunk {i} in stream {stream_id} from server")
                
                # Kết hợp tất cả chunks
                combined_audio = b''.join(all_chunks)
                logger.info(f"Playing audio from server (stream: {stream_id})")
                file_path = os.path.join(
                                    BASE_DIR, "debug", f"audio_response_from_server.wav")
                try:
                    audio_np = np.frombuffer(combined_audio, dtype=np.int16)
                    sf.write(
                        file_path, audio_np, audio_stream_buffers[stream_key]["sample_rate"], subtype='PCM_16')
                    logger.debug(
                        f"💾 Đã lưu file âm thanh: {file_path}")
                except Exception as e:
                    logger.error(
                        f"❌ Lỗi khi lưu file âm thanh: {e}")
                self.speaker.play_audio_data(combined_audio, audio_stream_buffers[stream_key]["sample_rate"])
                # self.speaker.play_file(file_path)
                    
                # Xóa buffer sau khi xử lý xong
                del audio_stream_buffers[stream_key]
                
        except Exception as e:
            logger.error(f"Error processing audio from server: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _cleanup_old_streams(self):
        """Kiểm tra và xử lý các audio streams bị timeout"""
        while True:
            try:
                current_time = time.time()
                streams_to_process = []
                
                # Kiểm tra các streams đã quá thời gian chờ
                for stream_key, stream_data in list(audio_stream_buffers.items()):
                    if current_time - stream_data["timestamp"] > STREAM_TIMEOUT:
                        if stream_data["received_chunks"] > 0:
                            logger.warning(f"Stream {stream_key} timed out with {stream_data['received_chunks']}/{stream_data['total_chunks']} chunks. Processing anyway.")
                            streams_to_process.append(stream_key)
                
                # Xử lý các streams bị timeout
                for stream_key in streams_to_process:
                    stream_data = audio_stream_buffers[stream_key]
                    
                    # Kết hợp các chunks theo thứ tự
                    all_chunks = []
                    for i in range(stream_data["total_chunks"]):
                        if i in stream_data["chunks"]:
                            all_chunks.append(stream_data["chunks"][i])
                    
                    # Kết hợp tất cả chunks
                    if all_chunks:
                        combined_audio = b''.join(all_chunks)
                        logger.info(f"Playing timed out audio from server (stream: {stream_key}, {len(all_chunks)}/{stream_data['total_chunks']} chunks)")
                        self.speaker.play_audio_data(combined_audio, stream_data["sample_rate"])
                    
                    # Xóa buffer sau khi xử lý
                    del audio_stream_buffers[stream_key]
                
                # Ngủ 1 giây trước khi kiểm tra lại
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error in cleanup thread: {e}")
                time.sleep(5)  # Ngủ dài hơn nếu có lỗi
    
    def handle_command(self, payload: dict):
        """Handle commands from server"""
        command = payload.get("command")
        if command == "send_sms":
            self.handle_send_sms(payload)

    def handle_send_sms(self, payload: dict):
        """
        Xử lý yêu cầu gửi SMS từ server.
        payload expected: { "command": "send_sms", "phoneNumber": "+84xxxxxxxxx", "message": "..." }
        """
        try:
            phone_number = payload.get("phone_number")
            message = payload.get("message")

            if not phone_number or not message:
                logger.error("Missing phoneNumber or message for send_sms command")
                return

            logger.info(f"Sending SMS to {phone_number}...")
            ok = self.gprs.send_test_sms(phone_number, message)
            if ok:
                logger.info("SMS sent successfully")
            else:
                logger.error("SMS sending failed")
        except Exception as e:
            logger.error(f"Error handling send_sms: {e}")
