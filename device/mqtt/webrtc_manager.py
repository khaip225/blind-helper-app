"""
WebRTC Manager cho MQTT Module
================================
Quản lý kết nối WebRTC với mobile app
"""

import asyncio
import json
import fractions
import time
import os
import sys
import platform
from typing import Optional, Callable
from collections import deque
import queue
import cv2
import aiohttp


from aiortc import (
    RTCPeerConnection, 
    RTCSessionDescription, 
    RTCIceCandidate,
    RTCConfiguration,
    RTCIceServer,
    MediaStreamTrack
)
from aiortc.contrib.media import MediaPlayer
from aiortc.sdp import candidate_from_sdp
import av
import numpy as np


from log import setup_logger
from container import container

logger = setup_logger(__name__)


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


class CameraVideoTrack(MediaStreamTrack):
    """
    Video track từ CameraDirect (OpenCV)
    """
    kind = "video"
    
    def __init__(self, camera, fps=30):
        super().__init__()
        self.camera = camera
        self._pts = 0
        self._fps = fps
        self._time_base = fractions.Fraction(1, 90000)  # 90kHz clock
        self._frame_interval = 1.0 / fps
        self._last_frame_time = 0
        logger.info(f"🎥 CameraVideoTrack initialized with {fps} FPS")
    
    async def recv(self):
        """Nhận frame từ camera và convert sang VideoFrame"""
        # FPS control
        current_time = time.time()
        elapsed = current_time - self._last_frame_time
        if elapsed < self._frame_interval:
            await asyncio.sleep(self._frame_interval - elapsed)
        
        # Lấy frame từ camera
        frame_bgr = self.camera.get_latest_frame()
        if frame_bgr is None:
            # Return white frame nếu chưa có frame
            frame_bgr = np.full((480, 640, 3), 255, dtype=np.uint8)
            if self._pts % 90 == 0:  # Log mỗi 3 giây (30fps * 3)
                logger.warning("⚠️ Camera frame is None, sending white frame")
        
        # Convert BGR (OpenCV) sang RGB (WebRTC)
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        
        # Resize nếu cần (để đảm bảo kích thước phù hợp)
        height, width = frame_rgb.shape[:2]
        if width != 640 or height != 480:
            frame_rgb = cv2.resize(frame_rgb, (640, 480))
        
        # Tạo VideoFrame từ numpy array
        video_frame = av.VideoFrame.from_ndarray(frame_rgb, format='rgb24')
        video_frame.pts = self._pts
        video_frame.time_base = self._time_base
        
        # Tăng timestamp
        self._pts += int(self._frame_interval * 90000)  # 90kHz clock
        self._last_frame_time = time.time()
        
        # Debug log mỗi 30 frames (1 giây)
        if self._pts % (90000 * 1) == 0:
            logger.debug(f"📹 Video frame sent: pts={self._pts}, size={width}x{height}")
        
        return video_frame


class PyAudioSourceTrack(MediaStreamTrack):
    """Audio track sử dụng PyAudio (tương tự audio_handler.py)"""
    kind = "audio"

    def __init__(self, rate=48000, channels=1, frames_per_buffer=960, device_index=None, gain=1.0, noise_gate=0):
        super().__init__()
        self._rate = rate
        self._channels = channels
        self._chunk = frames_per_buffer
        self._time_base = fractions.Fraction(1, rate)
        self._pts = 0
        self._gain = gain
        self._noise_gate = noise_gate
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
            logger.info(f"🎤 Using PyAudio microphone{device_info} with gain={self._gain}x, rate={self._rate}, noise_gate={self._noise_gate}")
        except Exception as e:
            logger.error(f"Failed to initialize PyAudio: {e}", exc_info=True)
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
        if self._gain != 1.0 or self._noise_gate > 0:
            # Convert to numpy for processing
            samples = np.frombuffer(data, dtype=np.int16).copy()
            
            # Log audio levels every 100 frames (~2 seconds at 48kHz/960 buffer)
            if self._frame_count % 100 == 1:
                rms_before = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
                max_before = np.max(np.abs(samples))
                logger.info(f"🎤 Audio levels BEFORE gain: RMS={rms_before:.0f}, Max={max_before}, Gain={self._gain}x")
            
            # Apply gain
            if self._gain != 1.0:
                samples = samples.astype(np.float32) * self._gain
            
            # Noise gate: suppress very quiet signals (reduce hiss/noise)
            if self._noise_gate > 0:
                samples[np.abs(samples) < self._noise_gate] = 0
            
            # Log audio levels after gain
            if self._frame_count % 100 == 1:
                rms_after = np.sqrt(np.mean(samples ** 2))
                max_after = np.max(np.abs(samples))
                logger.info(f"🔊 Audio levels AFTER gain: RMS={rms_after:.0f}, Max={max_after:.0f}, NoiseGate={self._noise_gate}")
            
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






class WebRTCManager:
    """Quản lý kết nối WebRTC"""
    
    # TURN server config
    METERED_API_KEY = '6cc0b031d2951fbd7ac079906c6b0470b02a'
    METERED_API_URL = f'https://pbl6.metered.live/api/v1/turn/credentials?apiKey={METERED_API_KEY}'
    
    def __init__(self, device_id: str, mqtt_client=None):
        """
        Khởi tạo WebRTC Manager
        
        Args:
            device_id: ID của thiết bị
            mqtt_client: MQTT client để gửi signaling messages
        """
        
        self.device_id = device_id
        self.mqtt_client = mqtt_client
        
        # Peer connection
        self.pc: Optional[RTCPeerConnection] = None
        
        # Media tracks
        self.video_player = None
        self.audio_player = None
        
        # ICE candidates buffer
        self.pending_ice_candidates = deque()
        
        # Event loop
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.webrtc_task = None
        
        # Callbacks
        self.on_audio_track: Optional[Callable] = None
        self.on_video_track: Optional[Callable] = None
        self.on_connection_state_change: Optional[Callable] = None
        
        # Cache for TURN credentials
        self.cached_ice_servers = None
        
        logger.info(f"✅ WebRTCManager initialized for device {device_id}")
    
    def set_mqtt_client(self, mqtt_client: "MQTTClient"):
        """Set MQTT client sau khi khởi tạo"""
        self.mqtt_client = mqtt_client
    
    async def fetch_turn_credentials(self):
        """Fetch TURN credentials from Metered.ca API"""
        # Return cached if available
        if self.cached_ice_servers:
            logger.info('[TURN] Using cached credentials')
            return self.cached_ice_servers
        
        try:
            logger.info('[TURN] Fetching credentials from Metered.ca...')
            async with aiohttp.ClientSession() as session:
                async with session.get(self.METERED_API_URL, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        raise Exception(f'HTTP {response.status}')
                    
                    credentials = await response.json()
                    
                    # Convert to RTCIceServer objects
                    ice_servers = []
                    for server in credentials:
                        urls = server.get('urls', [])
                        if not isinstance(urls, list):
                            urls = [urls]
                        
                        # Create RTCIceServer
                        ice_server_kwargs = {'urls': urls}
                        if 'username' in server:
                            ice_server_kwargs['username'] = server['username']
                        if 'credential' in server:
                            ice_server_kwargs['credential'] = server['credential']
                        
                        ice_servers.append(RTCIceServer(**ice_server_kwargs))
                        
                        # Log server types
                        for url in urls:
                            if url.startswith('stun:'):
                                logger.info(f'[TURN] 🌐 STUN: {url}')
                            elif url.startswith('turn:'):
                                logger.info(f'[TURN] 🔄 TURN: {url}')
                    
                    logger.info(f'[TURN] ✅ Fetched {len(ice_servers)} ICE servers')
                    
                    # Cache for reuse
                    self.cached_ice_servers = ice_servers
                    return ice_servers
                    
        except Exception as e:
            logger.error(f'[TURN] ❌ Failed to fetch credentials: {e}')
            # Fallback to Google STUN
            logger.info('[TURN] 📡 Falling back to Google STUN')
            return [
                RTCIceServer(urls=['stun:stun.l.google.com:19302']),
                RTCIceServer(urls=['stun:stun1.l.google.com:19302']),
            ]
    
    async def initialize_peer_connection(self):
        """Khởi tạo RTCPeerConnection"""
        try:
            # Đóng connection cũ nếu có
            if self.pc and self.pc.connectionState != "closed":
                await self.pc.close()
                logger.info("🔒 Closed existing peer connection")
            
            # Fetch TURN credentials
            logger.info("📡 Fetching TURN credentials...")
            ice_servers = await self.fetch_turn_credentials()
            
            # Tạo RTCPeerConnection với TURN servers
            configuration = RTCConfiguration(iceServers=ice_servers)
            self.pc = RTCPeerConnection(configuration=configuration)
            
            logger.info(f"✅ RTCPeerConnection created with {len(ice_servers)} ICE servers (STUN + TURN)")
            
            # Setup event handlers
            self._setup_event_handlers()
            
            # Setup media tracks
            await self._setup_media_tracks()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize peer connection: {e}", exc_info=True)
            return False
    
    def _setup_event_handlers(self):
        """Thiết lập các event handlers cho peer connection"""
        
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            state = self.pc.connectionState
            emoji = {
                "new": "🆕", 
                "connecting": "🔄", 
                "connected": "✅", 
                "disconnected": "⚠️", 
                "failed": "❌", 
                "closed": "🔒"
            }
            logger.info(f"{emoji.get(state, '❓')} Connection state: {state}")
            
            if self.on_connection_state_change:
                try:
                    if asyncio.iscoroutinefunction(self.on_connection_state_change):
                        await self.on_connection_state_change(state)
                    else:
                        self.on_connection_state_change(state)
                except Exception as e:
                    logger.error(f"Error in connection state callback: {e}", exc_info=True)
        
        @self.pc.on("track")
        async def on_track(track):
            logger.info(f"📥 Incoming track: kind={track.kind}, id={track.id}")
            
            if track.kind == "audio":
                if self.on_audio_track:
                    try:
                        await self.on_audio_track(track)
                    except Exception as e:
                        logger.error(f"Error in audio track callback: {e}", exc_info=True)
            
            elif track.kind == "video":
                if self.on_video_track:
                    try:
                        await self.on_video_track(track)
                    except Exception as e:
                        logger.error(f"Error in video track callback: {e}", exc_info=True)
        
        @self.pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            ice_state = self.pc.iceConnectionState
            emoji = {
                "new": "🆕", 
                "checking": "🔍", 
                "connected": "✅", 
                "completed": "🏁", 
                "failed": "❌", 
                "disconnected": "⚠️", 
                "closed": "🔒"
            }
            logger.info(f"{emoji.get(ice_state, '❓')} ICE connection state: {ice_state}")
            
            if ice_state == "connected":
                logger.info("🎉 ICE connection established! Media should start flowing now.")
                # Log which candidate pair was selected
                try:
                    if hasattr(self.pc, '_RTCPeerConnection__sctp') and self.pc._RTCPeerConnection__sctp:
                        sctp = self.pc._RTCPeerConnection__sctp
                        if hasattr(sctp, 'transport') and hasattr(sctp.transport, '_connection'):
                            ice_conn = sctp.transport._connection
                            if hasattr(ice_conn, 'selected_candidate_pair'):
                                pair = ice_conn.selected_candidate_pair
                                if pair:
                                    logger.info(f"✅ Selected candidate pair:")
                                    logger.info(f"   Local: {pair[0].type} {pair[0].host}:{pair[0].port}")
                                    logger.info(f"   Remote: {pair[1].type} {pair[1].host}:{pair[1].port}")
                except Exception as e:
                    logger.debug(f"Could not log selected candidate pair: {e}")
            elif ice_state == "completed":
                logger.info("🏁 ICE connection completed! All candidates checked.")
            elif ice_state == "failed":
                logger.error("❌ ICE connection FAILED! Check network/firewall settings.")
                logger.error("💡 Tips:")
                logger.error("   1. Ensure both devices are on same network OR")
                logger.error("   2. Use TURN server for relay (already enabled)")
                logger.error("   3. Check if TURN server is accessible from both ends")
                # Log all attempted candidates
                try:
                    if hasattr(self.pc, '_RTCPeerConnection__sctp') and self.pc._RTCPeerConnection__sctp:
                        sctp = self.pc._RTCPeerConnection__sctp
                        if hasattr(sctp, 'transport') and hasattr(sctp.transport, '_connection'):
                            ice_conn = sctp.transport._connection
                            local_cands = ice_conn.local_candidates if hasattr(ice_conn, 'local_candidates') else []
                            remote_cands = ice_conn.remote_candidates if hasattr(ice_conn, 'remote_candidates') else []
                            logger.error(f"📊 Local candidates: {len(local_cands)}")
                            for i, c in enumerate(local_cands[:5]):
                                logger.error(f"   {i+1}. {c.type}: {c.host}:{c.port}")
                            logger.error(f"📊 Remote candidates: {len(remote_cands)}")
                            for i, c in enumerate(remote_cands[:5]):
                                logger.error(f"   {i+1}. {c.type}: {c.host}:{c.port}")
                except Exception as e:
                    logger.debug(f"Could not log candidates: {e}")
        
        @self.pc.on("icegatheringstatechange")
        async def on_icegatheringstatechange():
            state = self.pc.iceGatheringState
            logger.info(f"📡 ICE gathering state: {state}")
            
            if state == "complete":
                # Debug: Check local description
                if self.pc.localDescription:
                    logger.debug(f"Local SDP has {len(self.pc.localDescription.sdp)} chars")
                else:
                    logger.warning("⚠️ No local description after ICE gathering complete")
        
        @self.pc.on("icecandidate")
        async def on_icecandidate(candidate):
            logger.info(f"🔔 on_icecandidate event triggered! candidate={candidate is not None}")  # ALWAYS log
            if candidate:
                cand_str = candidate.candidate
                logger.info(f"🔍 Generated candidate: {cand_str}")  # Changed to INFO to ensure visibility
                
                # Publish HOST và SRFLX candidates (skip RELAY nếu không có TURN)
                if "typ host" in cand_str:
                    # Filter IPv6 nếu muốn chỉ dùng IPv4 trong LAN
                    if ":" in cand_str and "typ host" in cand_str:
                        # IPv6 host candidate - có thể skip nếu chỉ muốn IPv4
                        logger.debug(f"⏭️ Skipping IPv6 HOST candidate: {cand_str[:80]}")
                        return
                    
                    logger.info(f"🏠 HOST candidate (will publish): {cand_str}")
                    
                    # Publish candidate qua MQTT
                    if self.mqtt_client:
                        payload = {
                            "candidate": candidate.candidate,
                            "sdpMid": candidate.sdpMid,
                            "sdpMLineIndex": candidate.sdpMLineIndex,
                        }
                        topic = f"device/{self.device_id}/webrtc/candidate"
                        self.mqtt_client.publish(topic, payload)
                        logger.info(f"📤 Published HOST candidate to {topic}")
                    else:
                        logger.warning("⚠️ MQTT client not available, cannot publish candidate")
                        
                elif "typ srflx" in cand_str:
                    # SRFLX từ STUN - cho phép để NAT traversal
                    logger.info(f"🌐 SRFLX candidate (will publish): {cand_str}")
                    
                    if self.mqtt_client:
                        payload = {
                            "candidate": candidate.candidate,
                            "sdpMid": candidate.sdpMid,
                            "sdpMLineIndex": candidate.sdpMLineIndex,
                        }
                        topic = f"device/{self.device_id}/webrtc/candidate"
                        self.mqtt_client.publish(topic, payload)
                        logger.info(f"📤 Published SRFLX candidate to {topic}")
                        
                elif "typ relay" in cand_str:
                    # RELAY từ TURN server - publish để NAT traversal
                    logger.info(f"🔄 RELAY candidate (TURN working!): {cand_str}")
                    
                    if self.mqtt_client:
                        payload = {
                            "candidate": candidate.candidate,
                            "sdpMid": candidate.sdpMid,
                            "sdpMLineIndex": candidate.sdpMLineIndex,
                        }
                        topic = f"device/{self.device_id}/webrtc/candidate"
                        self.mqtt_client.publish(topic, payload)
                        logger.info(f"📤 Published RELAY candidate to {topic}")
                else:
                    logger.info(f"⏭️ Skipping unknown candidate type: {cand_str[:80]}")
            else:
                logger.info("🏁 ICE gathering complete (null candidate)")
    
    async def _setup_media_tracks(self):
        """Setup audio và video tracks từ camera/microphone"""
        try:
            # Video track - Lấy camera từ container
            try:
                camera = container.get("camera")
                if camera:
                    video_track = CameraVideoTrack(camera, fps=30)
                    self.pc.addTrack(video_track)
                    logger.info(f"✅ Video track added from container camera")
                    self.video_player = video_track  # Store reference
                else:
                    logger.warning("⚠️ No camera in container - video call will be audio-only")
                    self.video_player = None
                    
            except Exception as e:
                logger.warning(f"⚠️ Could not setup video track: {e}", exc_info=True)
                self.video_player = None
            
            # Audio track - Microphone sử dụng PyAudio (tương tự audio_handler.py)
            try:
                # Lấy mic config từ config
                try:
                    from config import MIC_INDEX, AUDIO_SAMPLE_RATE
                    requested_rate = AUDIO_SAMPLE_RATE
                except ImportError:
                    requested_rate = 48000
                
                # Lấy gain và noise gate từ config (nếu có)
                try:
                    from config import MICROPHONE_GAIN, MICROPHONE_NOISE_GATE
                    mic_gain = MICROPHONE_GAIN
                    noise_gate = MICROPHONE_NOISE_GATE
                except ImportError:
                    # Default values optimized for WebRTC (lower gain, enable noise gate)
                    mic_gain = 1  # Giảm gain xuống 60% để tránh distortion/noise
                    noise_gate = 0  # Lọc noise dưới 200 (giảm tiếng hú/hiss)
                
                # 🎤 Jetson Nano: Tìm USB Audio Device (card 3) cho microphone
                mic_device_index = None
                if platform.system() == "Linux":
                    try:
                        import pyaudio
                        pa = pyaudio.PyAudio()
                        
                        # Find USB Audio Device with input channels
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
                    except ImportError:
                        logger.warning("PyAudio not available, cannot find USB mic device")
                    except Exception as e:
                        logger.warning(f"Error finding USB mic device: {e}")
                
                # ✅ Tạo audio track với retry logic nếu device bận
                max_retries = 3
                retry_delay = 0.5  # 500ms giữa các lần thử
                
                for attempt in range(max_retries):
                    try:
                        audio_track = PyAudioSourceTrack(
                            rate=requested_rate,
                            channels=1,
                            frames_per_buffer=960,
                            device_index=mic_device_index,
                            gain=mic_gain,
                            noise_gate=noise_gate
                        )
                        self.pc.addTrack(audio_track)
                        self.audio_player = audio_track  # Store reference
                        logger.info(f"✅ Audio track added using PyAudio (device={mic_device_index}, rate={requested_rate}, gain={mic_gain}x)")
                        break  # Success - thoát khỏi retry loop
                        
                    except Exception as e:
                        if "[Errno -9985]" in str(e) and attempt < max_retries - 1:
                            logger.warning(f"⚠️ Device unavailable (attempt {attempt+1}/{max_retries}), retrying in {retry_delay}s...")
                            import time as time_module
                            time_module.sleep(retry_delay)
                        else:
                            # Lần thử cuối hoặc lỗi khác
                            raise
                            
            except ImportError:
                logger.warning("⚠️ PyAudio not installed - microphone will not work")
                self.audio_player = None
            except Exception as e:
                logger.warning(f"⚠️ Could not setup audio track with PyAudio: {e}", exc_info=True)
                self.audio_player = None
                
        except Exception as e:
            logger.error(f"❌ Error setting up media tracks: {e}", exc_info=True)
    
    async def initiate_sos_call(self):
        """
        Khởi tạo cuộc gọi SOS từ device đến mobile:
        1. Khởi tạo peer connection
        2. Tạo offer
        3. Set local description
        4. Publish offer qua MQTT
        """
        try:
            logger.info("🆘 Starting SOS call initiation...")
            
            # 1. Initialize peer connection
            if not await self.initialize_peer_connection():
                logger.error("❌ Failed to initialize peer connection for SOS call")
                return False
            
            # 2. Create offer
            logger.info("📝 Creating offer...")
            offer = await self.pc.createOffer()
            
            # 3. Set local description
            logger.info("🔒 Setting local description...")
            await self.pc.setLocalDescription(offer)
            
            # ✅ Đợi và kiểm tra local description đã được set
            import asyncio
            max_wait = 5  # 5 giây
            waited = 0
            while not self.pc.localDescription and waited < max_wait:
                await asyncio.sleep(0.1)
                waited += 0.1
            
            if not self.pc.localDescription:
                logger.error("❌ Failed to set local description after 5s")
                return False
            
            logger.info(f"✅ Local description set: {len(self.pc.localDescription.sdp)} chars, state={self.pc.signalingState}")
            
            # 4. Publish offer to mobile via MQTT
            topic = f"device/{self.device_id}/webrtc/offer"
            logger.info(f"📤 Publishing SOS offer to mobile topic: {topic}")
            offer_message = {
                "type": "offer",
                "sdp": self.pc.localDescription.sdp,
                "callerId": self.device_id,
                "isEmergency": True  # Flag to indicate SOS call
            }
            
            # Don't json.dumps here - client.publish() will do it
            self.mqtt_client.publish(
                topic,
                offer_message,
                qos=1
            )
            
            logger.info("✅ SOS call offer sent successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initiate SOS call: {e}", exc_info=True)
            return False
    
    async def handle_offer(self, sdp: str, offer_type: str = "offer"):
        """
        Xử lý offer từ mobile
        
        Args:
            sdp: Session Description Protocol string
            offer_type: Loại offer (mặc định "offer")
        """
        try:
            logger.info("📞 Handling WebRTC offer from mobile")
            
            # Khởi tạo peer connection
            success = await self.initialize_peer_connection()
            if not success:
                logger.error("❌ Failed to initialize peer connection")
                return False
            
            # DON'T clear pending candidates - they were buffered while waiting for peer connection!
            # The candidates will be processed after setting remote description
            logger.info(f"📦 Found {len(self.pending_ice_candidates)} buffered candidates from mobile")
            
            # Set remote description (offer)
            logger.info("📥 Setting remote description (offer)...")
            remote_desc = RTCSessionDescription(sdp=sdp, type=offer_type)
            await self.pc.setRemoteDescription(remote_desc)
            logger.info("✅ Remote description set successfully")
            
            # Process any buffered ICE candidates
            await self._process_pending_candidates()
            
            # Create answer
            logger.info("📤 Creating answer...")
            answer = await self.pc.createAnswer()
            logger.info(f"✅ Answer created: type={answer.type}, sdp_length={len(answer.sdp)}")
            
            # Set local description - this will start ICE gathering
            await self.pc.setLocalDescription(answer)
            logger.info(f"✅ Local description set: type={self.pc.localDescription.type}")
            
            # ⚠️ CRITICAL: Wait for ICE gathering to complete
            logger.info("⏳ Waiting for ICE gathering to complete...")
            timeout = 10  # 10 seconds timeout
            start_time = time.time()
            while self.pc.iceGatheringState == "gathering" and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)
            
            logger.info(f"📡 ICE gathering finished: {self.pc.iceGatheringState}")
            
            # Extract candidates từ SDP và publish manually (aiortc có thể embed trong SDP)
            if self.pc.localDescription:
                sdp = self.pc.localDescription.sdp
                logger.info(f"📄 Extracting candidates from SDP (length={len(sdp)})")
                
                # Parse SDP để tìm candidates
                candidates_found = 0
                for line in sdp.split('\n'):
                    if line.startswith('a=candidate:'):
                        # Extract candidate string
                        cand_str = line.replace('a=candidate:', '').strip()
                        logger.info(f"🔍 Found candidate in SDP: {cand_str[:80]}")
                        
                        # Parse candidate
                        parts = cand_str.split()
                        if len(parts) >= 8:
                            foundation = parts[0]
                            component = parts[1]
                            protocol = parts[2]
                            priority = parts[3]
                            ip = parts[4]
                            port = parts[5]
                            typ = parts[6] if len(parts) > 6 else ""
                            
                            # Publish HOST, SRFLX và RELAY IPv4 candidates
                            if typ == "typ" and len(parts) > 7:
                                candidate_type = parts[7]
                                
                                # Skip IPv6
                                if ":" in ip:
                                    logger.debug(f"⏭️ Skipping IPv6 candidate: {ip}:{port}")
                                    continue
                                
                                # 🔥 Skip Docker bridge IP (172.17.0.0/16)
                                if ip.startswith("172.17.") or ip.startswith("172.18.") or ip.startswith("172.19."):
                                    logger.debug(f"⏭️ Skipping Docker bridge candidate: {ip}:{port}")
                                    continue
                                
                                # Publish HOST, SRFLX và RELAY
                                if candidate_type in ["host", "srflx", "relay"]:
                                    # Determine sdpMid và sdpMLineIndex từ SDP context
                                    # Tìm m= line trước đó để biết mid
                                    sdp_mid = "0"  # Default
                                    sdp_mline_index = 0
                                    
                                    # Try to find mid from SDP
                                    sdp_lines = sdp.split('\n')
                                    for i, l in enumerate(sdp_lines):
                                        if l == line:
                                            # Look backwards for m= line
                                            for j in range(i, -1, -1):
                                                if sdp_lines[j].startswith('m='):
                                                    sdp_mline_index = sdp_lines[:j+1].count('m=') - 1
                                                    break
                                                elif sdp_lines[j].startswith('a=mid:'):
                                                    sdp_mid = sdp_lines[j].replace('a=mid:', '').strip()
                                                    break
                                            break
                                    
                                    # Publish candidate
                                    if self.mqtt_client:
                                        payload = {
                                            "candidate": f"candidate:{cand_str}",
                                            "sdpMid": sdp_mid,
                                            "sdpMLineIndex": sdp_mline_index,
                                        }
                                        topic = f"device/{self.device_id}/webrtc/candidate"
                                        self.mqtt_client.publish(topic, payload)
                                        candidates_found += 1
                                        emoji = '🏠' if candidate_type == 'host' else ('🌐' if candidate_type == 'srflx' else '🔄')
                                        logger.info(f"📤 {emoji} Published {candidate_type.upper()} candidate from SDP: {ip}:{port} (mid={sdp_mid}, mline={sdp_mline_index})")
                
                if candidates_found > 0:
                    logger.info(f"✅ Published {candidates_found} candidates extracted from SDP")
                else:
                    logger.warning("⚠️ No candidates found in SDP or all were filtered")
            
            # Check if we have any local candidates
            try:
                # Try to access internal ICE transport to check candidates
                if hasattr(self.pc, '_RTCPeerConnection__sctp'):
                    sctp = self.pc._RTCPeerConnection__sctp
                    if sctp and hasattr(sctp, 'transport') and hasattr(sctp.transport, '_connection'):
                        ice_conn = sctp.transport._connection
                        local_candidates = ice_conn.local_candidates if hasattr(ice_conn, 'local_candidates') else []
                        logger.info(f"📊 Local candidates generated: {len(local_candidates)}")
                        for i, c in enumerate(local_candidates[:3]):
                            logger.info(f"   {i+1}. {c.type.upper()}: {c.host}:{c.port}")
                else:
                    logger.warning("⚠️ Cannot access internal ICE transport to check candidates")
            except Exception as e:
                logger.warning(f"⚠️ Error checking local candidates: {e}")
            
            # Publish answer via MQTT
            if self.mqtt_client:
                payload = {
                    "sdp": answer.sdp,
                    "type": answer.type
                }
                topic = f"device/{self.device_id}/webrtc/answer"
                self.mqtt_client.publish(topic, payload, qos=1, retain=False)
                logger.info(f"📤 Answer published to {topic}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error handling offer: {e}", exc_info=True)
            return False
    
    async def handle_answer(self, sdp: str, answer_type: str = "answer"):
        """
        Xử lý answer từ mobile khi device initiate SOS call
        
        Args:
            sdp: Session Description Protocol string
            answer_type: Loại answer (mặc định "answer")
        """
        try:
            logger.info("📥 Handling WebRTC answer from mobile")
            
            # Check if we have a peer connection with local offer
            if not self.pc:
                logger.error("❌ No peer connection exists")
                return False
            
            # ✅ Kiểm tra local description trước khi handle answer
            if not self.pc.localDescription:
                logger.error("❌ Cannot handle answer: no local description. Call may not have been initiated properly.")
                return False
            
            if self.pc.signalingState != "have-local-offer":
                logger.warning(f"⚠️ Unexpected signaling state: {self.pc.signalingState}, expected 'have-local-offer'")
                # Don't return False, try to proceed anyway
            
            # Set remote description (answer from mobile)
            answer = RTCSessionDescription(sdp=sdp, type=answer_type)
            await self.pc.setRemoteDescription(answer)
            logger.info(f"✅ Remote description set (type={answer.type})")
            
            # Process any buffered ICE candidates
            logger.info(f"📦 Processing {len(self.pending_ice_candidates)} buffered candidates...")
            while self.pending_ice_candidates:
                candidate_data = self.pending_ice_candidates.popleft()
                try:
                    await self.handle_ice_candidate(candidate_data)
                except Exception as e:
                    logger.error(f"❌ Error processing buffered candidate: {e}")
            
            logger.info("✅ Answer handled successfully, WebRTC negotiation complete")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error handling answer: {e}", exc_info=True)
            return False
    
    async def handle_ice_candidate(self, candidate_data: dict):
        """
        Xử lý ICE candidate từ mobile
        
        Args:
            candidate_data: Dictionary chứa candidate, sdpMid, sdpMLineIndex
        """
        try:
            # Buffer nếu peer connection chưa sẵn sàng
            if not self.pc:
                logger.info("⏳ Buffering ICE candidate (no peer connection)")
                self.pending_ice_candidates.append(candidate_data)
                return
            
            if not self.pc.remoteDescription:
                logger.info("⏳ Buffering ICE candidate (no remote description)")
                self.pending_ice_candidates.append(candidate_data)
                return
            
            # Get candidate string
            candidate_str = candidate_data.get("candidate")
            if not candidate_str:
                logger.debug("Empty ICE candidate (end-of-candidates)")
                return
            
            # Accept HOST, SRFLX và RELAY candidates từ mobile
            if "typ host" not in candidate_str and "typ srflx" not in candidate_str and "typ relay" not in candidate_str:
                logger.debug(f"⏭️ Skipping unknown candidate type: {candidate_str[:60]}")
                return
            
            # Filter IPv6 nếu muốn chỉ dùng IPv4 trong LAN
            if "typ host" in candidate_str and ":" in candidate_str:
                # IPv6 host candidate - có thể skip nếu chỉ muốn IPv4
                logger.debug(f"⏭️ Skipping IPv6 HOST candidate from mobile: {candidate_str[:60]}")
                return
            
            # Log candidate type
            cand_type = 'host' if 'typ host' in candidate_str else ('srflx' if 'typ srflx' in candidate_str else 'relay')
            emoji = '🏠' if cand_type == 'host' else ('🌐' if cand_type == 'srflx' else '🔄')
            logger.info(f"{emoji} Received {cand_type.upper()} candidate from mobile")
            
            # Parse candidate từ SDP string
            sdp_mid = candidate_data.get("sdpMid")
            sdp_mline_index = candidate_data.get("sdpMLineIndex")
            
            if candidate_from_sdp:
                # Parse candidate string thành RTCIceCandidate object
                candidate = candidate_from_sdp(candidate_str)
                candidate.sdpMid = sdp_mid
                candidate.sdpMLineIndex = sdp_mline_index
            else:
                # Fallback: Tạo object đơn giản (có thể không hoạt động)
                logger.warning("candidate_from_sdp not available, using workaround")
                # aiortc yêu cầu parse candidate, không thể dùng string trực tiếp
                # Bỏ qua candidate này
                logger.warning(f"Skipping candidate (cannot parse): {candidate_str[:60]}")
                return
            
            # Add candidate vào peer connection
            await self.pc.addIceCandidate(candidate)
            logger.info(f"✅ {cand_type.upper()} candidate added from mobile")
            
        except Exception as e:
            logger.error(f"❌ Error handling ICE candidate: {e}", exc_info=True)
 
    
    async def _process_pending_candidates(self):
        """Xử lý tất cả ICE candidates đang chờ"""
        if not self.pc or not self.pc.remoteDescription:
            logger.warning(f"⚠️ Cannot process candidates: pc={self.pc is not None}, remoteDesc={self.pc.remoteDescription if self.pc else None}")
            return
        
        total = len(self.pending_ice_candidates)
        logger.info(f"📋 Processing {total} buffered ICE candidates...")
        
        processed = 0
        skipped = 0
        errors = 0
        
        while self.pending_ice_candidates:
            candidate_data = self.pending_ice_candidates.popleft()
            try:
                # Check candidate type before processing
                cand_str = candidate_data.get("candidate", "")
                if not cand_str:
                    skipped += 1
                    logger.debug("⏭️ Empty candidate")
                    continue
                    
                # Log what we're about to process
                cand_type = 'host' if 'typ host' in cand_str else ('srflx' if 'typ srflx' in cand_str else ('relay' if 'typ relay' in cand_str else 'unknown'))
                logger.debug(f"🔍 Processing buffered {cand_type.upper()} candidate: {cand_str[:60]}")
                
                await self.handle_ice_candidate(candidate_data)
                processed += 1
            except Exception as e:
                errors += 1
                logger.error(f"❌ Error processing pending candidate: {e}", exc_info=True)
        
        logger.info(f"✅ Finished processing buffered candidates: {processed} added, {skipped} skipped, {errors} errors (total={total})")
    
    async def close(self):
        """Đóng peer connection"""
        try:
            if self.pc and self.pc.connectionState != "closed":
                await self.pc.close()
                logger.info("🔒 Peer connection closed")
            
            # Stop video track (CameraVideoTrack không cần stop vì camera được quản lý bởi container)
            if self.video_player:
                try:
                    if hasattr(self.video_player, 'stop'):
                        self.video_player.stop()
                except Exception:
                    pass
            
            # Stop audio player
            if self.audio_player:
                try:
                    self.audio_player.stop()
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"Error closing peer connection: {e}")
    
    def start_event_loop(self):
        """Khởi động event loop riêng cho WebRTC trong background thread"""
        if self.loop and self.loop.is_running():
            return  # Đã chạy rồi
        
        loop_ref = {'loop': None}  # Use dict để tránh closure issue
        
        def run_event_loop():
            """Chạy event loop trong thread riêng"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop_ref['loop'] = loop
                self.loop = loop  # Set vào instance
                logger.info("🔄 WebRTC event loop started in background thread")
                loop.run_forever()
            except Exception as e:
                logger.error(f"❌ WebRTC event loop error: {e}", exc_info=True)
            finally:
                if loop_ref['loop']:
                    try:
                        loop_ref['loop'].close()
                        logger.info("🔒 WebRTC event loop closed")
                    except Exception:
                        pass
        
        # Start event loop thread
        import threading
        self.loop_thread = threading.Thread(target=run_event_loop, daemon=True)
        self.loop_thread.start()
        
        # Đợi một chút để loop khởi động
        import time
        max_wait = 10  # Tối đa đợi 1 giây
        waited = 0
        while waited < max_wait and (not self.loop or not self.loop.is_running()):
            time.sleep(0.1)
            waited += 1
        
        if self.loop and self.loop.is_running():
            logger.info("✅ WebRTC event loop is running")
        else:
            logger.warning("⚠️ WebRTC event loop may not be ready yet")
    
    def run_async(self, coro):
        """Chạy coroutine trong event loop"""
        # Đảm bảo event loop đã chạy
        if not self.loop or not self.loop.is_running():
            self.start_event_loop()
            # Đợi thêm một chút
            import time
            time.sleep(0.2)
        
        if self.loop and self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            return future
        else:
            # Fallback: chạy trong thread riêng
            logger.warning("⚠️ Event loop not available, using fallback")
            return asyncio.run(coro)

