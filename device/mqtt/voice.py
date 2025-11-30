"""
Voice Streaming
===============
"""

import base64
import time
from config import *
from container import container
from module.voice_mic import VoiceStreamer as BaseVoiceStreamer
from log import setup_logger
from module.voice_speaker import VoiceSpeaker

logger = setup_logger(__name__)


class VoiceMQTT:
    """Voice recording and streaming via MQTT"""

    def __init__(self, mqtt_client=None):
        self.mqtt_client = mqtt_client
        self.base_streamer = BaseVoiceStreamer(
            MIC_INDEX, sample_rate=AUDIO_SAMPLE_RATE, chunk_duration_ms=AUDIO_CHUNK_MS)

    def set_mqtt_client(self, mqtt_client):
        """Set MQTT client for sending audio"""
        self.mqtt_client = mqtt_client

    def start_continuous_listening(self):
        """Start continuous voice listening with VAD"""
        def on_speech_complete(audio_data, duration):
            logger.info(f"Speech detected: {duration:.1f}s")
            speaker: VoiceSpeaker = container.get("speaker")
            speaker.play_file(os.path.join(BASE_DIR, "audio", "processing.wav"))
            self._send_audio_chunks(audio_data)

        self.base_streamer.set_callbacks(on_speech_complete=on_speech_complete)
        self.base_streamer.start_listening()

    def stop_continuous_listening(self):
        """Stop continuous voice listening"""
        self.base_streamer.stop_listening()
    
    def pause_vad(self):
        """Tạm dừng VAD (Voice Activity Detection) - Dùng khi có cuộc gọi WebRTC"""
        logger.info("⏸️ Pausing VAD for WebRTC call")
        self.base_streamer.stop_listening()
    
    def resume_vad(self):
        """Tiếp tục VAD sau khi cuộc gọi WebRTC kết thúc"""
        logger.info("▶️ Resuming VAD after WebRTC call")
        self.start_continuous_listening()

    def _send_audio_chunks(self, audio_data: bytes):
        """Send audio data as chunks via MQTT"""
        if not self.mqtt_client:
            return

        stream_id = f"voice_{int(time.time() * 1000)}"
        chunk_size = 1024 * 8  # 8KB per chunk  
        total_chunks = (len(audio_data) + chunk_size - 1) // chunk_size

        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, len(audio_data))
            chunk_data = audio_data[start:end]

            payload = {
                "deviceId": DEVICE_ID,
                "streamId": stream_id,
                "chunkIndex": i,
                "totalChunks": total_chunks,
                "isLast": (i == total_chunks - 1),
                "timestamp": int(time.time() * 1000),
                "format": "pcm16le",
                "sampleRate": AUDIO_SAMPLE_RATE,
                "data": base64.b64encode(chunk_data).decode()
            }

            self.mqtt_client.publish(TOPICS['device_stt'], payload, qos=1)
        logger.info(f"Sent {total_chunks} chunks to MQTT")
        
    def stop(self):
        """Stop voice streaming"""
        self.base_streamer.stop_listening()