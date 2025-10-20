import asyncio
import json
import logging
import platform
import sys
import threading

import paho.mqtt.client as mqtt
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer
from types import SimpleNamespace
try:
    from aiortc.sdp import candidate_from_sdp  # type: ignore
except Exception:
    candidate_from_sdp = None

# --- Cấu hình logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webrtc_simulator")

# --- Biến toàn cục ---
client = None
pc = None
player = None
# QUAN TRỌNG: Sửa ID này để khớp với ID bạn nhập trên app
DEVICE_ID = "jetson"
MAIN_LOOP: asyncio.AbstractEventLoop | None = None

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

async def handle_message_async(topic, payload):
    global pc
    logger.info(f"Received on {topic}")
    try:
        data = json.loads(payload)

        if topic.endswith("/webrtc/offer"):
            logger.info("Received offer from mobile, preparing answer...")
            await initialize_peer_connection()
            if pc:
                await pc.setRemoteDescription(RTCSessionDescription(sdp=data["sdp"], type=data["type"]))
                await answer_call()

        elif topic.endswith("/webrtc/answer"):
            if pc:
                logger.info("Received answer from mobile.")
                await pc.setRemoteDescription(RTCSessionDescription(sdp=data["sdp"], type=data["type"]))

        elif topic.endswith("/webrtc/candidate"):
            if not pc:
                logger.warning("ICE candidate received but PeerConnection not ready.")
                return
            if not data:
                logger.info("Received empty ICE candidate payload; ignoring.")
                return

            logger.info("Received ICE candidate from mobile.")
            try:
                candidate_str = data.get("candidate")
                sdp_mid = data.get("sdpMid")
                sdp_mline_index = data.get("sdpMLineIndex")

                if candidate_str and candidate_from_sdp:
                    # Parse the candidate string to get a Candidate object
                    parsed = candidate_from_sdp(candidate_str)
                    parsed.sdpMid = sdp_mid
                    parsed.sdpMLineIndex = sdp_mline_index
                    await pc.addIceCandidate(parsed)
                    logger.info("ICE candidate added successfully.")
                elif candidate_str:
                    # If parser not available, log and skip (aiortc needs proper Candidate object)
                    logger.warning(f"candidate_from_sdp not available; skipping ICE candidate: {candidate_str[:50]}...")
                else:
                    logger.info("ICE candidate payload missing 'candidate'; skipping.")
            except Exception as ce:
                logger.error(f"Failed to add ICE candidate: {ce}")

    except Exception as e:
        logger.error(f"Error handling message on {topic}: {e}")

def on_message(client, userdata, msg):
    if MAIN_LOOP and MAIN_LOOP.is_running():
        asyncio.run_coroutine_threadsafe(
            handle_message_async(msg.topic, msg.payload.decode()),
            MAIN_LOOP,
        )
    else:
        logger.error("Main asyncio loop is not available. Dropping MQTT message.")

async def initialize_peer_connection():
    global pc, player
    if pc and pc.connectionState != "closed":
        await pc.close()
    if player:
        try:
            player.stop()
        except Exception:
            pass

    options = {"framerate": "30", "video_size": "640x480"}
    if platform.system() == "Windows":
        try:
            player = MediaPlayer("video=Integrated Webcam", format="dshow", options=options)
        except Exception as e:
            logger.warning(f"Could not open 'Integrated Webcam' ({e}). Please check your camera name.")
            return
    elif platform.system() == "Darwin":
        player = MediaPlayer("default:none", format="avfoundation", options=options)
    else:
        player = MediaPlayer("/dev/video0", format="v4l2", options=options)

    try:
        from aiortc import RTCConfiguration, RTCIceServer  # type: ignore
        pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[
            RTCIceServer(urls=[
                "stun:stun.l.google.com:19302",
                "stun:stun1.l.google.com:19302",
            ])
        ]))
    except Exception:
        pc = RTCPeerConnection()

    if player and player.video:
        logger.info("Webcam opened successfully.")
        pc.addTrack(player.video)
    else:
        logger.error("COULD NOT OPEN WEBCAM.")
        return

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            logger.info("Generated ICE candidate.")
            payload = json.dumps({
                "candidate": candidate.candidate,
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            })
            client.publish(f"device/{DEVICE_ID}/webrtc/candidate", payload)

async def start_sos_call():
    global pc
    if pc and pc.connectionState != "closed":
        return

    await initialize_peer_connection()
    if pc:
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        payload = json.dumps({"sdp": offer.sdp, "type": offer.type})
        client.publish(f"device/{DEVICE_ID}/webrtc/offer", payload)
        logger.info("Offer published.")

async def answer_call():
    global pc
    if pc:
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        payload = json.dumps({"sdp": answer.sdp, "type": answer.type})
        client.publish(f"device/{DEVICE_ID}/webrtc/answer", payload)
        logger.info("Answer published.")

async def main():
    global client, MAIN_LOOP
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    try:
        client.ws_set_options(path="/mqtt")
    except Exception:
        pass
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("broker.hivemq.com", 8000, 60)

    MAIN_LOOP = asyncio.get_running_loop()

    client.loop_start()

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

    print("\nNhấn Enter để BẮT ĐẦU cuộc gọi SOS (Device -> Mobile)")
    print("Simulator cũng đang lắng nghe cuộc gọi từ Mobile...")

    while True:
        try:
            if sos_requested.is_set():
                logger.info("Initiating SOS call...")
                await start_sos_call()
                sos_requested.clear()

            await asyncio.sleep(1)
        except KeyboardInterrupt:
            break

    logger.info("Shutting down...")
    if player:
        try:
            player.stop()
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
        logger.info("Simulator stopped by user.")

