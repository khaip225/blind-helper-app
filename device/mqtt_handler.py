"""MQTT message handling (simplified)."""
import asyncio
import json
import os
import uuid
import paho.mqtt.client as mqtt
from config import (
    logger, DEVICE_ID, state,
    BROKER_TRANSPORT, BROKER_WS_PATH, BROKER_USE_TLS,
    BROKER_HOST, BROKER_PORT, MQTT_USER, MQTT_PASS
)
import ssl
from webrtc_handler import initialize_peer_connection, add_ice_candidate, process_pending_candidates, answer_call

def on_connect(client, userdata, flags, rc, properties=None):
    """Callback khi kết nối MQTT thành công.

    Compatible with paho callbacks that call either:
      on_connect(client, userdata, flags, rc)
    or (MQTT v5):
      on_connect(client, userdata, flags, rc, properties)
    """
    # `rc` is the CONNACK return code (0 = success)
    try:
        code = int(rc)
    except Exception:
        code = rc

    if code != 0:
        logger.error(f"Failed to connect to MQTT: rc={code}")
        return
    logger.info(f"MQTT Connected with reason code {code}")
    topics = [
        (f"device/{DEVICE_ID}/webrtc/offer", 1),
        (f"device/{DEVICE_ID}/webrtc/answer", 1),
        (f"device/{DEVICE_ID}/webrtc/candidate", 0),
    ]
    for topic_tuple in topics:
        if isinstance(topic_tuple, tuple):
            topic, qos = topic_tuple
            client.subscribe(topic, qos=qos)
            logger.info(f"Subscribed to {topic} (QoS={qos})")
        else:
            # Fallback for backward compatibility
            client.subscribe(topic_tuple)
            logger.info(f"Subscribed to {topic_tuple}")

async def handle_message_async(topic, payload):
    """Process MQTT messages asynchronously."""
    logger.info(f"Received on {topic}")
    
    # Parse JSON
    try:
        data = json.loads(payload)
        msg_type = data.get("type", "unknown")
        logger.info(f"   Message type: {msg_type}")
    except Exception as e:
        logger.warning(f"   Failed to parse JSON: {e}")
        return
    
    try:
        if topic.endswith("/webrtc/offer"):
            logger.info("Offer received from mobile; preparing answer")
            state.pending_ice_candidates.clear()
            
            await initialize_peer_connection()
            if state.pc:
                from aiortc import RTCSessionDescription
                await state.pc.setRemoteDescription(
                    RTCSessionDescription(sdp=data["sdp"], type=data["type"])
                )
                logger.info("Remote description set")
                
                await process_pending_candidates()
                await answer_call()

        elif topic.endswith("/webrtc/answer"):
            if state.pc:
                logger.info("Answer received from mobile")
                try:
                    if state.pc.signalingState != "have-local-offer":
                        if state.pc.signalingState == "stable":
                            logger.info("Already stable; ignoring duplicate/late answer")
                        else:
                            logger.warning(f"⚠️ Ignoring answer in signalingState={state.pc.signalingState}")
                        return
                    sdp = data.get("sdp")
                    if state.last_remote_answer_sdp == sdp:
                        logger.info("Duplicate answer SDP; ignoring")
                        return
                    from aiortc import RTCSessionDescription
                    await state.pc.setRemoteDescription(
                        RTCSessionDescription(sdp=sdp, type=data.get("type", "answer"))
                    )
                    state.last_remote_answer_sdp = sdp
                    logger.info("Remote answer description set")
                    await process_pending_candidates()
                except Exception as e:
                    logger.error(f"❌ Failed to apply answer: {e}")

        elif topic.endswith("/webrtc/candidate"):
            # Buffer candidates if PC not ready yet
            if not state.pc:
                buffer_count = len(state.pending_ice_candidates) + 1
                logger.info(f"ICE candidate buffered (PC not ready) total={buffer_count}")
                state.pending_ice_candidates.append(data)
                
                # Warning if too many candidates buffered without offer
                if buffer_count == 10:
                    logger.warning("10 candidates buffered but no offer yet")
                elif buffer_count >= 20:
                    logger.warning(f"{buffer_count} candidates buffered; still waiting for offer")
                return
            
            if not state.pc.remoteDescription:
                buffer_count = len(state.pending_ice_candidates) + 1
                logger.info(f"ICE candidate buffered (waiting remote description) total={buffer_count}")
                state.pending_ice_candidates.append(data)
                return
            
            await add_ice_candidate(data)
        
        else:
            # 🔍 Debug: Log unhandled topics
            logger.warning(f"Unhandled topic: {topic}")
            logger.warning("Expected: /webrtc/offer,/webrtc/answer,/webrtc/candidate")

    except Exception as e:
        logger.error(f"❌ Error handling message on {topic}: {e}", exc_info=True)

def on_message(client, userdata, msg):
    """Callback khi nhận message MQTT"""
    if state.main_loop and state.main_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            handle_message_async(msg.topic, msg.payload.decode()),
            state.main_loop,
        )
    else:
        logger.error("Main asyncio loop is not available. Dropping MQTT message.")

def setup_mqtt_client():
    """Thiết lập MQTT client"""
    # Use hardcoded values from config.py (already set there)
    transport = BROKER_TRANSPORT
    # Allow overriding client id via env var `MQTT_CLIENT_ID`.
    # By default use the fixed `DEVICE_ID` so you can input a predictable id for testing.
    env_client_id = os.getenv("MQTT_CLIENT_ID")
    if env_client_id:
        chosen_client_id = env_client_id
    else:
        chosen_client_id = DEVICE_ID

    # Create client using the chosen client id
    try:
        # Request a persistent session on the device side as well (clean_session=False)
        client = mqtt.Client(client_id=chosen_client_id, clean_session=False, transport=transport)
    except TypeError:
        # Older paho versions may have different signature; fall back and try to force non-clean session
        client = mqtt.Client(chosen_client_id, mqtt.CallbackAPIVersion.VERSION2, transport=transport)
        try:
            # attempt to set internal flag for older clients
            setattr(client, '_clean_session', False)
        except Exception:
            pass
    # Ensure websocket path is set to the configured value
    if transport == "websockets":
        try:
            client.ws_set_options(path=BROKER_WS_PATH)
            logger.info(f"MQTT websocket path set to '{BROKER_WS_PATH}'")
        except Exception as e:
            logger.warning(f"Failed to set websocket path options: {e}")
    # Auth
    if MQTT_USER:
        try:
            client.username_pw_set(MQTT_USER, MQTT_PASS)
        except Exception:
            logger.warning("Could not apply MQTT username/password")
    # TLS: enforce based on config
    if BROKER_USE_TLS:
        try:
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
            client.tls_insecure_set(True)
            logger.info("MQTT TLS enabled (insecure allowed)")
        except Exception as e:
            logger.warning(f"Failed to enable TLS: {e}")
    
    client.on_connect = on_connect
    client.on_message = on_message
    logger.info(f"MQTT client configured: client_id={chosen_client_id}, host={BROKER_HOST}, port={BROKER_PORT}, transport={transport}, ws_path={BROKER_WS_PATH}, tls={BROKER_USE_TLS}, user={MQTT_USER}")
    
    return client
