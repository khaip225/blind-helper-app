import asyncio
import json
import logging
import os
import fractions
import queue
import time
import platform
import sys
import threading
from collections import deque

import aioice.stun
import paho.mqtt.client as mqtt
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.mediastreams import MediaStreamTrack
import av
import numpy as np
from aiortc.contrib.media import MediaPlayer, MediaRecorder

try:
    from aiortc.sdp import candidate_from_sdp
except Exception:
    candidate_from_sdp = None

# Fix STUN private address check
def is_private_address(addr):
    if addr.startswith("10.") or addr.startswith("192.168."):
        return True
    if addr.startswith("172."):
        try:
            second_octet = int(addr.split(".")[1])
            return 16 <= second_octet <= 31
        except:
            return False
    return False

aioice.stun.is_private_address = is_private_address

# --- Cấu hình logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc_simulator")

# --- Biến toàn cục ---
client = None
pc = None
player = None
audio_player = None
recorder = None  # For recording incoming audio to verify reception
pyaudio_track = None  # Optional PyAudio capture track
playback_task = None  # asyncio Task for playing incoming audio
_pyaudio_out = None  # PyAudio instance for playback
_pyaudio_out_stream = None  # PyAudio output stream
DEVICE_ID = "jetson"
MAIN_LOOP: asyncio.AbstractEventLoop | None = None
pending_ice_candidates = deque()
last_ice_restart_ts = 0.0  # throttle repeated ICE restarts
ICE_RESTART_COOLDOWN = 15.0  # seconds

# Runtime flags (configurable via CLI or environment)
FORCE_TURN = False
FORCE_IPV4 = False
TURN_URLS = []  # list of URLs (e.g., ["turns:your.turn.server:443?transport=tcp"])
TURN_USERNAME = None
TURN_PASSWORD = None
PLAYBACK_GAIN = 1.0  # default playback gain
PLAYBACK_OUTPUT_RATE = 48000  # output sample rate for local playback

def on_connect(client, userdata, flags, reason_code, properties):
    if getattr(reason_code, "is_failure", False):
        logger.error(f"Failed to connect to MQTT: {reason_code}")
        return
    logger.info(f"MQTT Connected with reason code {reason_code}")
    topics = [
        f"mobile/{DEVICE_ID}/webrtc/offer",
        f"mobile/{DEVICE_ID}/webrtc/answer",
        f"mobile/{DEVICE_ID}/webrtc/candidate",
    ]
    for topic in topics:
        client.subscribe(topic)
        logger.info(f"Subscribed to {topic}")

async def process_pending_candidates():
    """Xử lý tất cả ICE candidates đang chờ"""
    global pc, pending_ice_candidates
    
    if not pc or not pc.remoteDescription:
        return
    
    processed = 0
    while pending_ice_candidates:
        data = pending_ice_candidates.popleft()
        try:
            await add_ice_candidate(data)
            processed += 1
        except Exception as e:
            logger.error(f"Error processing pending candidate: {e}")
    
    if processed > 0:
        logger.info(f"✅ Processed {processed} pending ICE candidates")

async def add_ice_candidate(data):
    """Thêm ICE candidate vào peer connection"""
    global pc
    
    if not data or not data.get("candidate"):
        logger.debug("Received empty ICE candidate (end-of-candidates)")
        return
    
    try:
        candidate_str = data.get("candidate")
        sdp_mid = data.get("sdpMid")
        sdp_mline_index = data.get("sdpMLineIndex")
        if candidate_str and candidate_from_sdp:
            parsed = candidate_from_sdp(candidate_str)
            # Filtering based on flags
            if FORCE_TURN and getattr(parsed, "type", None) != "relay":
                logger.info("⏭️ Skipping non-RELAY remote candidate due to --force-turn")
                return
            if FORCE_IPV4 and ":" in getattr(parsed, "ip", ""):
                logger.info("⏭️ Skipping IPv6 remote candidate due to --force-ipv4")
                return

            parsed.sdpMid = sdp_mid
            parsed.sdpMLineIndex = sdp_mline_index
            await pc.addIceCandidate(parsed)
            
            # Log chi tiết loại candidate
            if "typ relay" in candidate_str:
                logger.info(f"🔄 RELAY candidate added: {candidate_str[:80]}...")
            elif "typ srflx" in candidate_str:
                logger.info(f"🌐 SRFLX candidate added: {candidate_str[:80]}...")
            elif "typ host" in candidate_str:
                logger.info(f"🏠 HOST candidate added: {candidate_str[:80]}...")
            else:
                logger.info(f"✅ ICE candidate added: {candidate_str[:60]}...")
        else:
            # Fallback: simple string-based filtering
            if FORCE_TURN and " typ relay" not in candidate_str:
                logger.info("⏭️ Skipping non-RELAY remote candidate due to --force-turn")
                return
            if FORCE_IPV4 and ":" in candidate_str:
                logger.info("⏭️ Skipping IPv6 remote candidate due to --force-ipv4")
                return
            await pc.addIceCandidate(RTCIceCandidate(sdpMid=sdp_mid, sdpMLineIndex=sdp_mline_index, candidate=candidate_str))
            logger.info(f"✅ ICE candidate added (no parser): {candidate_str[:60]}...")
    except Exception as e:
        logger.error(f"Failed to add ICE candidate: {e}")

async def handle_message_async(topic, payload):
    global pc, pending_ice_candidates
    logger.info(f"📨 Received on {topic}")
    
    try:
        data = json.loads(payload)

        if topic.endswith("/webrtc/offer"):
            logger.info("📞 Received offer from mobile, preparing answer...")
            pending_ice_candidates.clear()
            
            await initialize_peer_connection()
            if pc:
                await pc.setRemoteDescription(
                    RTCSessionDescription(sdp=data["sdp"], type=data["type"])
                )
                logger.info("✅ Remote description set successfully.")
                
                await process_pending_candidates()
                await answer_call()

        elif topic.endswith("/webrtc/answer"):
            if pc:
                logger.info("📞 Received answer from mobile.")
                await pc.setRemoteDescription(
                    RTCSessionDescription(sdp=data["sdp"], type=data["type"])
                )
                logger.info("✅ Remote description set successfully.")
                await process_pending_candidates()

        elif topic.endswith("/webrtc/candidate"):
            if not pc:
                logger.warning("⚠️ ICE candidate received but PeerConnection not ready.")
                return
            
            if not pc.remoteDescription:
                logger.warning("⚠️ ICE candidate buffered (waiting for remote description)")
                pending_ice_candidates.append(data)
                return
            
            await add_ice_candidate(data)

    except Exception as e:
        logger.error(f"❌ Error handling message on {topic}: {e}", exc_info=True)

def on_message(client, userdata, msg):
    if MAIN_LOOP and MAIN_LOOP.is_running():
        asyncio.run_coroutine_threadsafe(
            handle_message_async(msg.topic, msg.payload.decode()),
            MAIN_LOOP,
        )
    else:
        logger.error("Main asyncio loop is not available. Dropping MQTT message.")

async def initialize_peer_connection():
    global pc, player, audio_player, pyaudio_track
    
    if pc and pc.connectionState != "closed":
        await pc.close()
    if player:
        try:
            player.stop()
        except Exception:
            pass
    if audio_player:
        try:
            audio_player.stop()
        except Exception:
            pass
    
    # Configure camera and audio
    options = {"framerate": "30", "video_size": "640x480"}
    audio_player = None
    pyaudio_track = None
    
    if platform.system() == "Windows":
        # Windows: Try to open video+audio from webcam (many webcams have built-in mic)
        try:
            # Common webcam names on Windows
            video_devices = [
                "Integrated Webcam",
                "USB Camera",
                "HD Webcam",
                "Webcam",
            ]
            
            for video_name in video_devices:
                try:
                    # Try to open video with audio from same device
                    player = MediaPlayer(f"video={video_name}:audio={video_name}", format="dshow", options=options)
                    logger.info(f"📹 Using camera with audio: {video_name}")
                    break
                except Exception:
                    # If audio fails, try video-only
                    try:
                        player = MediaPlayer(f"video={video_name}", format="dshow", options=options)
                        logger.info(f"📹 Using camera (video only): {video_name}")
                        break
                    except Exception:
                        continue
            
            if not player:
                logger.warning("Could not find any camera. Trying default...")
                player = MediaPlayer("video=0", format="dshow", options=options)
        except Exception as e:
            logger.error(f"Could not open webcam ({e}). Please check your camera.")
            return
        
        # Windows microphone: Prefer PyAudio if available, fallback to DirectShow
        try:
            try:
                import pyaudio  # type: ignore

                class PyAudioSourceTrack(MediaStreamTrack):
                    kind = "audio"

                    def __init__(self, rate=48000, channels=1, frames_per_buffer=960):
                        super().__init__()
                        self._rate = rate
                        self._channels = channels
                        self._chunk = frames_per_buffer
                        self._time_base = fractions.Fraction(1, rate)
                        self._pts = 0
                        self._queue: "queue.Queue[bytes]" = queue.Queue(maxsize=100)

                        self._pa = pyaudio.PyAudio()
                        self._stream = self._pa.open(
                            format=pyaudio.paInt16,
                            channels=self._channels,
                            rate=self._rate,
                            input=True,
                            frames_per_buffer=self._chunk,
                            stream_callback=self._on_audio,
                        )
                        self._stream.start_stream()
                        logger.info("🎤 Using PyAudio microphone (default input device)")

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

                    async def recv(self) -> av.AudioFrame:  # type: ignore[override]
                        # Wait for next chunk of audio from the callback
                        loop = asyncio.get_running_loop()
                        data: bytes = await loop.run_in_executor(None, self._queue.get)
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

                    def stop(self) -> None:  # type: ignore[override]
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

                pyaudio_track = PyAudioSourceTrack(rate=48000, channels=1, frames_per_buffer=960)
            except ImportError:
                pyaudio_track = None

            if not pyaudio_track:
                # Fallback to DirectShow if PyAudio not available or failed
                audio_opened = False
                for idx in range(5):
                    try:
                        audio_player = MediaPlayer(
                            f"audio=@device_cm_{{{idx}}}",
                            format="dshow",
                            options={"channels": "1", "sample_rate": "48000"},
                        )
                        logger.info(f"🎤 Using DirectShow microphone device index: {idx}")
                        audio_opened = True
                        break
                    except Exception:
                        continue

                if not audio_opened:
                    audio_devices = [
                        "Microphone Array",
                        "Microphone",
                        "Realtek Audio",
                    ]

                    for audio_name in audio_devices:
                        try:
                            audio_player = MediaPlayer(
                                f"audio={audio_name}",
                                format="dshow",
                                options={"channels": "1", "sample_rate": "48000"},
                            )
                            logger.info(f"🎤 Using DirectShow microphone: {audio_name}")
                            audio_opened = True
                            break
                        except Exception:
                            continue

                if not audio_opened:
                    logger.warning("Could not open any microphone device with DirectShow")
        except Exception as e:
            logger.warning(f"Could not open microphone: {e}")
    
    elif platform.system() == "Darwin":
        player = MediaPlayer("default:none", format="avfoundation", options=options)
        # macOS: Audio might be included with video
        logger.info("📹 Using macOS camera")
    
    else:
        # Linux (Jetson Nano) - Video
        camera_devices = ["/dev/video0", "/dev/video1"]
        player = None
        
        for device in camera_devices:
            try:
                player = MediaPlayer(device, format="v4l2", options=options)
                logger.info(f"📹 Using camera at {device}")
                break
            except Exception as e:
                logger.warning(f"Could not open {device}: {e}")
        
        if not player:
            logger.error("❌ Could not open any camera device!")
            return
        
        # Linux: Audio device (separate for Jetson Nano)
        if platform.system() == "Linux":
            # Try pulse audio first, then ALSA
            audio_options = {"channels": "1", "sample_rate": "48000"}
            try:
                # Try PulseAudio (easier on Jetson)
                audio_player = MediaPlayer("default", format="pulse", options=audio_options)
                logger.info("🎤 Using PulseAudio for microphone")
            except Exception as e1:
                logger.warning(f"PulseAudio not available: {e1}")
                try:
                    # Try ALSA hw:0,0
                    audio_player = MediaPlayer("hw:0,0", format="alsa", options=audio_options)
                    logger.info("🎤 Using ALSA hw:0,0 for microphone")
                except Exception as e2:
                    logger.warning(f"ALSA hw:0,0 not available: {e2}")
                    try:
                        # Try plughw:0,0 (with automatic conversion)
                        audio_player = MediaPlayer("plughw:0,0", format="alsa", options=audio_options)
                        logger.info("🎤 Using ALSA plughw:0,0 for microphone")
                    except Exception as e3:
                        logger.warning(f"Could not open any audio device: {e3}")

    # Create peer connection with UPDATED ICE servers
    try:
        from aiortc import RTCConfiguration, RTCIceServer
        
        # Base STUN
        ice_servers = [
            RTCIceServer(urls=[
                "stun:stun.l.google.com:19302",
                "stun:stun1.l.google.com:19302",
            ]),
        ]

        # Optional TURN from config
        if TURN_URLS and TURN_USERNAME and TURN_PASSWORD:
            ice_servers.append(
                RTCIceServer(
                    urls=TURN_URLS,
                    username=TURN_USERNAME,
                    credential=TURN_PASSWORD,
                )
            )
            logger.info(f"🔐 TURN configured with {len(TURN_URLS)} URL(s)")
        else:
            logger.warning("No TURN configured. Cross-network calls may fail. Use --turn-urls/--turn-username/--turn-password.")
        
        pc = RTCPeerConnection(
            configuration=RTCConfiguration(iceServers=ice_servers)
        )
        logger.info("✅ RTCPeerConnection created with ICE servers")
        logger.info(f"   - {len(ice_servers)} ICE servers configured")
        logger.info("   Note: aiortc does not support iceTransportPolicy, will try all candidates")
        
    except Exception as e:
        logger.error(f"❌ Failed to create PC with ICE config: {e}")
        pc = RTCPeerConnection()

    # Add video and audio tracks
    if player and player.video:
        pc.addTrack(player.video)
        logger.info("✅ Video track added")
    else:
        logger.error("❌ COULD NOT OPEN WEBCAM.")
        return
    
    # Add audio track (prefer PyAudio if created, else MediaPlayer if available)
    if pyaudio_track is not None:
        pc.addTrack(pyaudio_track)
        logger.info("✅ Audio track added (PyAudio)")
    elif audio_player and audio_player.audio:
        # Use MediaPlayer audio
        pc.addTrack(audio_player.audio)
        logger.info("✅ Audio track added (MediaPlayer)")
    elif player and player.audio:
        # Use camera audio
        pc.addTrack(player.audio)
        logger.info("✅ Audio track added (Camera audio)")
    else:
        logger.warning("⚠️ No audio available - video call will be video-only")

    # Event handlers with detailed logging
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        state = pc.connectionState
        emoji = {"new": "🆕", "connecting": "🔄", "connected": "✅", "disconnected": "⚠️", "failed": "❌", "closed": "🔒"}
        logger.info(f"{emoji.get(state, '❓')} Connection state: {state}")
        
        if state == "failed":
            logger.error("❌ WebRTC connection FAILED!")
            logger.error("💡 Troubleshooting tips:")
            logger.error("   1. Check if mobile app has internet connection")
            logger.error("   2. Try using mobile data instead of WiFi (or vice versa)")
            logger.error("   3. Check firewall settings on both devices")
            logger.error("   4. Ensure both devices can reach TURN servers")
            # Try an ICE restart to recover if the remote still listens
            try:
                await schedule_ice_restart("connectionstate=failed")
            except Exception as e:
                logger.warning(f"ICE restart attempt failed to schedule: {e}")
        elif state == "connected":
            logger.info("🎉 WebRTC connection ESTABLISHED!")
        elif state == "disconnected":
            # Network glitch or consent freshness timeout; attempt restart
            try:
                await schedule_ice_restart("connectionstate=disconnected")
            except Exception as e:
                logger.warning(f"ICE restart attempt failed to schedule: {e}")

    @pc.on("track")
    async def on_track(track):
        # Log incoming tracks (audio/video)
        try:
            logger.info(f"📥 Incoming track: kind={track.kind}, id={track.id}")
            if track.kind == "audio":
                global recorder
                # Record incoming audio to a file to verify it's arriving
                try:
                    recorder = MediaRecorder(f"received_{DEVICE_ID}_audio.wav")
                    await recorder.start()
                    recorder.addTrack(track)
                    logger.info(f"🎧 Recording incoming audio to received_{DEVICE_ID}_audio.wav")
                except Exception as e:
                    logger.warning(f"Could not start recorder for incoming audio: {e}")

                # Also attempt local playback via PyAudio if available
                async def _play_incoming_audio(t):
                    global _pyaudio_out, _pyaudio_out_stream
                    try:
                        try:
                            import pyaudio  # type: ignore
                        except ImportError:
                            logger.warning("PyAudio not installed - skipping local audio playback")
                            return

                        if _pyaudio_out is None:
                            _pyaudio_out = pyaudio.PyAudio()

                        current_cfg = (None, None)  # (rate, channels)
                        resampler = None
                        resample_cfg = (None, None)  # (rate, channels)
                        while True:
                            frame: av.AudioFrame = await t.recv()
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
                                    logger.info(
                                        f"🎛️ Resampler configured -> rate={PLAYBACK_OUTPUT_RATE}, channels={out_channels}"
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed to create resampler, using raw frames: {e}")
                                    resampler = None

                            try:
                                if resampler is not None:
                                    out_frames = resampler.resample(frame)
                                    # concatenate all returned frames
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

                            # Apply gain with clipping
                            if PLAYBACK_GAIN != 1.0:
                                amplified = (pcm.astype(np.int32) * PLAYBACK_GAIN)
                                amplified = np.clip(amplified, -32768, 32767).astype(np.int16)
                                pcm_bytes = amplified.tobytes()
                            else:
                                pcm_bytes = pcm.tobytes()

                            if current_cfg != (rate, channels) or _pyaudio_out_stream is None:
                                # (Re)open output stream with new format
                                try:
                                    if _pyaudio_out_stream is not None:
                                        _pyaudio_out_stream.stop_stream()
                                        _pyaudio_out_stream.close()
                                except Exception:
                                    pass
                                _pyaudio_out_stream = _pyaudio_out.open(
                                    format=pyaudio.paInt16,
                                    channels=channels,
                                    rate=rate,
                                    output=True,
                                    frames_per_buffer=960,
                                )
                                logger.info(f"🔊 Audio playback started (rate={rate}, channels={channels})")
                                current_cfg = (rate, channels)

                            try:
                                _pyaudio_out_stream.write(pcm_bytes)
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

                global playback_task
                if playback_task is None or playback_task.done():
                    playback_task = asyncio.create_task(_play_incoming_audio(track))
                    logger.info("🔈 Local audio playback task started")
            elif track.kind == "video":
                logger.info("🎥 Incoming video track received")
        except Exception as e:
            logger.error(f"Error in on_track handler: {e}")

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        state = pc.iceConnectionState
        emoji = {"new": "🆕", "checking": "🔍", "connected": "✅", "completed": "🏁", "failed": "❌", "disconnected": "⚠️", "closed": "🔒"}
        logger.info(f"{emoji.get(state, '❓')} ICE connection state: {state}")
        # If consent freshness expires, state often flips to 'disconnected' then 'failed'.
        # Proactively attempt an ICE restart (throttled).
        if state in ("disconnected", "failed"):
            try:
                await schedule_ice_restart(f"iceconnectionstate={state}")
            except Exception as e:
                logger.warning(f"ICE restart attempt failed to schedule: {e}")

    @pc.on("icegatheringstatechange")
    async def on_icegatheringstatechange():
        state = pc.iceGatheringState
        logger.info(f"📡 ICE gathering state: {state}")

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            cand_str = candidate.candidate

            # Optional filtering before publishing
            try:
                if candidate_from_sdp:
                    parsed = candidate_from_sdp(cand_str)
                    if FORCE_TURN and getattr(parsed, "type", None) != "relay":
                        logger.info("⏭️ Not publishing non-RELAY local candidate due to --force-turn")
                        return
                    if FORCE_IPV4 and ":" in getattr(parsed, "ip", ""):
                        logger.info("⏭️ Not publishing IPv6 local candidate due to --force-ipv4")
                        return
                else:
                    if FORCE_TURN and " typ relay" not in cand_str:
                        logger.info("⏭️ Not publishing non-RELAY local candidate due to --force-turn")
                        return
                    if FORCE_IPV4 and ":" in cand_str:
                        logger.info("⏭️ Not publishing IPv6 local candidate due to --force-ipv4")
                        return
            except Exception:
                pass

            # Log với emoji tùy loại
            if "typ relay" in cand_str:
                logger.info(f"🔄 RELAY candidate (TURN): {cand_str[:80]}...")
            elif "typ srflx" in cand_str:
                logger.info(f"🌐 SRFLX candidate (STUN): {cand_str[:80]}...")
            elif "typ host" in cand_str:
                logger.info(f"🏠 HOST candidate (Local): {cand_str[:80]}...")
            else:
                logger.info(f"🎯 ICE candidate: {cand_str[:80]}...")

            payload = json.dumps({
                "candidate": candidate.candidate,
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            })
            topic = f"device/{DEVICE_ID}/webrtc/candidate"
            client.publish(topic, payload)
            logger.info(f"📤 Published ICE candidate to {topic}")
        else:
            logger.info("🏁 ICE candidate gathering complete (end-of-candidates)")

async def start_sos_call():
    """Khởi tạo cuộc gọi từ device"""
    global pc, pending_ice_candidates
    
    if pc and pc.connectionState != "closed":
        logger.warning("⚠️ Connection already exists, skipping...")
        return

    logger.info("🆘 Starting SOS call...")
    pending_ice_candidates.clear()
    await initialize_peer_connection()
    
    if pc:
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        payload = json.dumps({"sdp": offer.sdp, "type": offer.type})
        client.publish(f"device/{DEVICE_ID}/webrtc/offer", payload)
        logger.info("📤 Offer published to MQTT")

async def answer_call():
    """Trả lời cuộc gọi từ mobile"""
    global pc
    
    if pc:
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        payload = json.dumps({"sdp": answer.sdp, "type": answer.type})
        client.publish(f"device/{DEVICE_ID}/webrtc/answer", payload)
        logger.info("📤 Answer published to MQTT")

async def schedule_ice_restart(reason: str = ""):
    """Attempt an ICE restart by sending a new offer.

    This can recover from consent freshness expiry or transient network changes.
    Throttled by ICE_RESTART_COOLDOWN to avoid renegotiation storms.
    """
    global pc, last_ice_restart_ts
    now = time.monotonic()
    if now - last_ice_restart_ts < ICE_RESTART_COOLDOWN:
        logger.info(
            f"⏳ Skipping ICE restart (cooldown {ICE_RESTART_COOLDOWN}s). Reason: {reason}"
        )
        return
    if not pc or pc.connectionState == "closed":
        logger.info("⚪ ICE restart skipped: no active PeerConnection")
        return
    try:
        logger.info(f"🔁 Attempting ICE restart (reason='{reason}')…")
        offer = await pc.createOffer(iceRestart=True)
        await pc.setLocalDescription(offer)

        payload = json.dumps({"sdp": offer.sdp, "type": offer.type})
        topic = f"device/{DEVICE_ID}/webrtc/offer"
        client.publish(topic, payload)
        last_ice_restart_ts = now
        logger.info(f"📤 ICE-restart offer published to {topic}")
    except Exception as e:
        logger.warning(f"ICE restart failed: {e}")

async def main():
    global client, MAIN_LOOP, DEVICE_ID, FORCE_TURN, FORCE_IPV4, TURN_URLS, TURN_USERNAME, TURN_PASSWORD, PLAYBACK_GAIN

    # Parse CLI args / env
    import argparse
    parser = argparse.ArgumentParser(description="WebRTC Video Call Simulator")
    parser.add_argument("--device-id", default=os.environ.get("DEVICE_ID", DEVICE_ID))
    parser.add_argument("--force-turn", action="store_true", default=os.environ.get("FORCE_TURN", "false").lower() in ("1", "true", "yes"))
    parser.add_argument("--force-ipv4", action="store_true", default=os.environ.get("FORCE_IPV4", "false").lower() in ("1", "true", "yes"))
    parser.add_argument("--turn-urls", default=os.environ.get("TURN_URLS", ""), help="Comma-separated TURN URLs (e.g., turns:turn.example.com:443?transport=tcp)")
    parser.add_argument("--turn-username", default=os.environ.get("TURN_USERNAME"))
    parser.add_argument("--turn-password", default=os.environ.get("TURN_PASSWORD"))
    parser.add_argument("--playback-gain", type=float, default=float(os.environ.get("PLAYBACK_GAIN", "1.0")), help="Gain multiplier for incoming audio playback (default 1.0)")
    parser.add_argument("--playback-rate", type=int, default=int(os.environ.get("PLAYBACK_RATE", "48000")), help="Output sample rate for local audio playback (e.g. 44100 or 48000)")
    args = parser.parse_args()

    DEVICE_ID = args.device_id
    FORCE_TURN = bool(args.force_turn)
    FORCE_IPV4 = bool(args.force_ipv4)
    TURN_URLS = [u.strip() for u in args.turn_urls.split(",") if u.strip()] if args.turn_urls else []
    TURN_USERNAME = args.turn_username
    TURN_PASSWORD = args.turn_password
    PLAYBACK_GAIN = max(0.1, min(args.playback_gain, 10.0))  # clamp gain 0.1 - 10.0
    global PLAYBACK_OUTPUT_RATE
    PLAYBACK_OUTPUT_RATE = int(args.playback_rate)

    # Startup banner
    print("\n" + "="*60)
    print("🚀 WebRTC Video Call Simulator")
    print("="*60)
    print(f"📱 Device ID: {DEVICE_ID}")
    print(f"🌐 MQTT Broker: broker.hivemq.com:8000")
    if FORCE_TURN or FORCE_IPV4:
        print("🔧 Active flags:")
        print(f"   - FORCE_TURN: {FORCE_TURN}")
        print(f"   - FORCE_IPV4: {FORCE_IPV4}")
    if TURN_URLS:
        print(f"   - TURN_URLS: {TURN_URLS}")
        print(f"   - TURN_USERNAME set: {bool(TURN_USERNAME)}")
        print(f"   - TURN_PASSWORD set: {bool(TURN_PASSWORD)}")
    print(f"🔊 Playback gain: {PLAYBACK_GAIN}")
    print(f"🎚️ Playback rate: {PLAYBACK_OUTPUT_RATE} Hz")
    print("📹 Press Enter to START SOS call (Device -> Mobile)")
    print("📞 Also listening for incoming calls from Mobile...")
    print("="*60 + "\n")
    
    # Setup MQTT client
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    try:
        client.ws_set_options(path="/mqtt")
    except Exception:
        pass
    
    client.on_connect = on_connect
    client.on_message = on_message
    
    logger.info("🔌 Connecting to MQTT broker...")
    client.connect("broker.hivemq.com", 8000, 60)

    MAIN_LOOP = asyncio.get_running_loop()
    client.loop_start()

    # Setup user input handler
    sos_requested = asyncio.Event()

    def user_input_handler():
        while True:
            try:
                sys.stdin.readline()
                MAIN_LOOP.call_soon_threadsafe(sos_requested.set)
            except (KeyboardInterrupt, EOFError):
                break

    input_thread = threading.Thread(target=user_input_handler, daemon=True)
    input_thread.start()

    try:
        while True:
            if sos_requested.is_set():
                await start_sos_call()
                sos_requested.clear()

            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("🛑 Shutting down...")
        if player:
            try:
                player.stop()
            except Exception:
                pass
        if audio_player:
            try:
                audio_player.stop()
            except Exception:
                pass
        # Clean up PyAudio track if used
        if 'pyaudio_track' in globals() and pyaudio_track is not None:
            try:
                pyaudio_track.stop()
            except Exception:
                pass
        # Stop local playback task and close PyAudio output
        if 'playback_task' in globals() and playback_task is not None:
            try:
                playback_task.cancel()
            except Exception:
                pass
        if '_pyaudio_out_stream' in globals() and _pyaudio_out_stream is not None:
            try:
                _pyaudio_out_stream.stop_stream()
                _pyaudio_out_stream.close()
            except Exception:
                pass
        if '_pyaudio_out' in globals() and _pyaudio_out is not None:
            try:
                _pyaudio_out.terminate()
            except Exception:
                pass
        if recorder:
            try:
                await recorder.stop()
            except Exception:
                pass
        if pc:
            await pc.close()
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Simulator stopped by user.")