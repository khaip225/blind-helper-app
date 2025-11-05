import asyncio
import json
import logging
import platform
import sys
import threading
from collections import deque
import os

import aioice.stun
import paho.mqtt.client as mqtt
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer, MediaRecorder

try:
    from aiortc.sdp import candidate_from_sdp
except Exception:
    candidate_from_sdp = None

# Import PyAudio track for Windows microphone (more reliable than DirectShow)
PYAUDIO_AVAILABLE = False
if platform.system() == "Windows":
    try:
        from pyaudio_track import PyAudioTrack
        PYAUDIO_AVAILABLE = True
    except ImportError:
        pass  # Will try DirectShow fallback

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

# Ensure ALSA uses system config on Linux to avoid 'Unknown PCM' due to bad env
if platform.system() == "Linux":
    os.environ.setdefault("ALSA_CONFIG_PATH", "/usr/share/alsa/alsa.conf")
    os.environ.setdefault("ALSA_CONFIG_DIR", "/usr/share/alsa")

# --- Cấu hình logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc_simulator")

# --- Biến toàn cục ---
client = None
pc = None
player = None
audio_player = None
audio_track = None  # PyAudio track for Windows microphone
recorder = None  # For recording incoming audio to verify reception
DEVICE_ID = "jetson"
MAIN_LOOP: asyncio.AbstractEventLoop | None = None
pending_ice_candidates = deque()

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
            logger.warning(f"Cannot parse ICE candidate: {candidate_str[:50]}...")
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
    global pc, player, audio_player, audio_track
    
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
    
    # Initialize audio_track as None
    audio_track = None

    # Configure camera and audio
    options = {"framerate": "30", "video_size": "640x480"}
    audio_player = None
    
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
        
        # Windows: Try PyAudio first (more reliable), fallback to DirectShow
        if PYAUDIO_AVAILABLE:
            try:
                # Use PyAudio for microphone capture - much more reliable on Windows
                from pyaudio_track import list_audio_devices
                list_audio_devices()  # Show available devices in console
                
                # This will be a MediaStreamTrack, not a MediaPlayer
                audio_track = PyAudioTrack(sample_rate=48000, channels=1, chunk_size=960)
                logger.info("🎤 Using PyAudio for microphone capture (more reliable)")
            except Exception as e:
                logger.warning(f"Could not initialize PyAudio: {e}")
                audio_track = None
        else:
            # Fallback to DirectShow if PyAudio not available
            try:
                audio_opened = False
                for idx in range(5):
                    try:
                        audio_player = MediaPlayer(f"audio=@device_cm_{{{idx}}}", format="dshow", options={"channels": "1", "sample_rate": "48000"})
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
                            audio_player = MediaPlayer(f"audio={audio_name}", format="dshow", options={"channels": "1", "sample_rate": "48000"})
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
        
        # Linux (Jetson Nano): Audio device selection
        if platform.system() == "Linux":
            # Try PulseAudio first (if available), then ALSA with your USB card (card 3)
            channels = os.environ.get("MIC_CHANNELS", "1")
            sample_rate = os.environ.get("MIC_RATE", "48000")
            audio_options = {"channels": channels, "sample_rate": sample_rate}

            # Allow override via env, e.g. MIC_DEVICE=plughw:3,0 or MIC_DEVICE=sysdefault:CARD=Device_1
            mic_env = os.environ.get("MIC_DEVICE") or os.environ.get("AUDIO_INPUT")
            if mic_env:
                try:
                    if mic_env.startswith(("hw:", "plughw:", "sysdefault:", "dsnoop:", "hw:CARD=", "plughw:CARD=")):
                        audio_player = MediaPlayer(mic_env, format="alsa", options=audio_options)
                        logger.info(f"🎤 Using ALSA device from env: {mic_env}")
                    else:
                        audio_player = MediaPlayer(mic_env, format="pulse", options=audio_options)
                        logger.info(f"🎤 Using PulseAudio source from env: {mic_env}")
                except Exception as e:
                    logger.warning(f"Env audio device '{mic_env}' failed: {e}")
                    audio_player = None

            # PulseAudio default source
            if not audio_player:
                try:
                    audio_player = MediaPlayer("default", format="pulse", options=audio_options)
                    logger.info("🎤 Using PulseAudio default microphone")
                except Exception as e1:
                    logger.warning(f"PulseAudio not available: {e1}")
                    audio_player = None

            # ALSA: prefer your USB on card 3, device 0
            if not audio_player:
                alsa_candidates = [
                    "plughw:3,0",  # USB Audio Device (card 3)
                    "hw:3,0",
                    "sysdefault:CARD=Device_1",
                    "dsnoop:CARD=Device_1,DEV=0",
                    # Fallback to another USB you have (card 2)
                    "plughw:2,0",
                    "hw:2,0",
                    "sysdefault:CARD=Device",
                    "dsnoop:CARD=Device,DEV=0",
                ]
                last_err = None
                for dev in alsa_candidates:
                    try:
                        audio_player = MediaPlayer(dev, format="alsa", options=audio_options)
                        logger.info(f"🎤 Using ALSA microphone: {dev}")
                        break
                    except Exception as e:
                        last_err = e
                        logger.debug(f"ALSA try {dev} failed: {e}")
                        audio_player = None
                if not audio_player:
                    logger.warning(f"Could not open any ALSA audio device: {last_err}")

    # Create peer connection with UPDATED ICE servers
    try:
        from aiortc import RTCConfiguration, RTCIceServer
        
        # Sử dụng nhiều TURN servers khác nhau để tăng khả năng kết nối
        ice_servers = [
            # Google STUN (luôn reliable)
            RTCIceServer(urls=[
                "stun:stun.l.google.com:19302",
                "stun:stun1.l.google.com:19302",
            ]),
            # ExpressTurn TURN Server (Your credentials) - UDP + TCP + TLS
            RTCIceServer(
                urls=[
                    "turn:relay1.expressturn.com:3478",
                    "turn:relay1.expressturn.com:3478?transport=tcp",
                    "turns:relay1.expressturn.com:5349",
                ],
                username="000000002076506456",
                credential="bK8A/K+WGDw/tYcuvM9/5xCnEZs=",
            ),
            # Twilio STUN/TURN (public free tier)
            RTCIceServer(
                urls=[
                    "turn:global.turn.twilio.com:3478?transport=udp",
                    "turn:global.turn.twilio.com:3478?transport=tcp",
                    "turn:global.turn.twilio.com:443?transport=tcp",
                ],
                username="f4b4035eaa76f4a55de5f4351567653ee4ff6fa97b50b6b334fcc1be9c27212d",
                credential="w1uxM55V9yVoqyVFjt+mxDBV0F87AUCemaYVQGxsPLw=",
            ),
        ]
        
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
    
    # Add audio track (handle both PyAudio track and MediaPlayer)
    if platform.system() == "Windows" and PYAUDIO_AVAILABLE and 'audio_track' in locals() and audio_track:
        # Use PyAudio track directly (it's already a MediaStreamTrack)
        pc.addTrack(audio_track)
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
        elif state == "connected":
            logger.info("🎉 WebRTC connection ESTABLISHED!")

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
            elif track.kind == "video":
                logger.info("🎥 Incoming video track received")
        except Exception as e:
            logger.error(f"Error in on_track handler: {e}")

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        state = pc.iceConnectionState
        emoji = {"new": "🆕", "checking": "🔍", "connected": "✅", "completed": "🏁", "failed": "❌", "disconnected": "⚠️", "closed": "🔒"}
        logger.info(f"{emoji.get(state, '❓')} ICE connection state: {state}")

    @pc.on("icegatheringstatechange")
    async def on_icegatheringstatechange():
        state = pc.iceGatheringState
        logger.info(f"📡 ICE gathering state: {state}")

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            cand_str = candidate.candidate
            
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

async def main():
    global client, MAIN_LOOP
    
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

    print("\n" + "="*60)
    print("🚀 WebRTC Video Call Simulator (Jetson Nano)")
    print("="*60)
    print(f"📱 Device ID: {DEVICE_ID}")
    print(f"🌐 MQTT Broker: broker.hivemq.com:8000")
    print("📹 Press Enter to START SOS call (Device -> Mobile)")
    print("📞 Also listening for incoming calls from Mobile...")
    print("="*60 + "\n")

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
        # Clean up PyAudio track if exists
        if 'audio_track' in globals() and audio_track:
            try:
                audio_track.stop()
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