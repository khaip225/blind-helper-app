"""
Xử lý WebRTC
"""
import asyncio
import json
import time
from collections import deque
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, RTCConfiguration, RTCIceServer
from config import logger, state, DEVICE_ID, FORCE_TURN, FORCE_IPV4, TURN_URLS, TURN_USERNAME, TURN_PASSWORD, ICE_RESTART_COOLDOWN, ICE_CANDIDATE_POOL_SIZE
from video_handler import MonitoredVideoTrack, setup_video_player, monitor_video
from audio_handler import setup_audio_player, handle_incoming_audio_track
from monitored_audio_track import MonitoredAudioTrack

try:
    from aiortc.sdp import candidate_from_sdp
except Exception:
    candidate_from_sdp = None

async def process_pending_candidates():
    """Xử lý tất cả ICE candidates đang chờ"""
    if not state.pc or not state.pc.remoteDescription:
        return
    
    processed = 0
    while state.pending_ice_candidates:
        data = state.pending_ice_candidates.pop(0)
        try:
            await add_ice_candidate(data)
            processed += 1
        except Exception as e:
            logger.error(f"Error processing pending candidate: {e}")
    
    if processed > 0:
        logger.info(f"✅ Processed {processed} pending ICE candidates")

async def add_ice_candidate(data):
    """Thêm ICE candidate vào peer connection"""
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
            await state.pc.addIceCandidate(parsed)
            
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
            await state.pc.addIceCandidate(
                RTCIceCandidate(sdpMid=sdp_mid, sdpMLineIndex=sdp_mline_index, candidate=candidate_str)
            )
            logger.info(f"✅ ICE candidate added (no parser): {candidate_str[:60]}...")
    except Exception as e:
        logger.error(f"Failed to add ICE candidate: {e}")

async def schedule_ice_restart(reason: str = ""):
    """Attempt an ICE restart by closing and recreating the connection"""
    now = time.monotonic()
    if now - state.last_ice_restart_ts < ICE_RESTART_COOLDOWN:
        logger.info(f"⏳ Skipping ICE restart (cooldown {ICE_RESTART_COOLDOWN}s). Reason: {reason}")
        return
    if not state.pc or state.pc.connectionState == "closed":
        logger.info("⚪ ICE restart skipped: no active PeerConnection")
        return
    try:
        logger.info(f"🔁 Attempting ICE restart (reason='{reason}')…")
        # aiortc doesn't support iceRestart parameter, so we recreate the connection
        logger.info("🔄 Closing existing connection and creating new offer...")
        
        # Just create a new offer (this will trigger ICE gathering again)
        offer = await state.pc.createOffer()
        await state.pc.setLocalDescription(offer)

        payload = json.dumps({"sdp": offer.sdp, "type": offer.type})
        # Device should publish to `mobile/{DEVICE_ID}` so the app (which subscribes to mobile/...) receives it
        topic = f"mobile/{DEVICE_ID}/webrtc/offer"
        state.client.publish(topic, payload)
        state.last_ice_restart_ts = now
        logger.info(f"📤 New offer published to {topic}")
    except Exception as e:
        logger.warning(f"ICE restart failed: {e}")

async def initialize_peer_connection():
    """Khởi tạo peer connection"""
    # Close existing connections
    if state.pc and state.pc.connectionState != "closed":
        await state.pc.close()
    if state.player:
        try:
            state.player.stop()
        except Exception:
            pass
    if state.audio_player:
        try:
            state.audio_player.stop()
        except Exception:
            pass
    
    # Setup video player
    state.player = setup_video_player()
    if not state.player or not state.player.video:
        logger.error("❌ COULD NOT OPEN WEBCAM.")
        return
    
    # Setup audio player
    state.audio_player, state.pyaudio_track = setup_audio_player()
    
    # Create peer connection with ICE servers
    try:
        ice_servers = []
        
        # 🔥 Chỉ dùng Metered.ca STUN/TURN - KHÔNG dùng Google STUN
        # Metered.ca STUN đã bao gồm trong TURN_URLS (stun:stun.relay.metered.ca:80)
        if TURN_URLS and TURN_USERNAME and TURN_PASSWORD:
            ice_servers.append(
                RTCIceServer(
                    urls=TURN_URLS,  # Bao gồm cả STUN và TURN của Metered.ca
                    username=TURN_USERNAME,
                    credential=TURN_PASSWORD,
                )
            )
            logger.info(f"🔐 Metered.ca STUN/TURN configured with {len(TURN_URLS)} URL(s)")
            logger.info(f"   URLs: {', '.join(TURN_URLS)}")
            logger.info(f"   Username: {TURN_USERNAME}")
        else:
            logger.error("⚠️ No TURN configured! WebRTC will likely fail.")
        
        # ⚠️ aiortc KHÔNG hỗ trợ iceCandidatePoolSize (chỉ có trong browser/react-native)
        state.pc = RTCPeerConnection(
            configuration=RTCConfiguration(
                iceServers=ice_servers
            )
        )
        logger.info(f"✅ RTCPeerConnection created with {len(ice_servers)} ICE server group(s)")
        
    except Exception as e:
        logger.error(f"❌ Failed to create PC with ICE config: {e}")
        state.pc = RTCPeerConnection()

    # Add video track
    if state.player and state.player.video:
        monitored = MonitoredVideoTrack(state.player.video)
        state.pc.addTrack(monitored)
        logger.info("✅ Video track added (monitored)")
    
    # Add audio track with monitoring
    if state.pyaudio_track is not None:
        monitored_audio = MonitoredAudioTrack(state.pyaudio_track)
        state.pc.addTrack(monitored_audio)
        logger.info("✅ Audio track added (PyAudio - monitored)")
    elif state.audio_player and state.audio_player.audio:
        monitored_audio = MonitoredAudioTrack(state.audio_player.audio)
        state.pc.addTrack(monitored_audio)
        logger.info("✅ Audio track added (MediaPlayer - monitored)")
    elif state.player and state.player.audio:
        monitored_audio = MonitoredAudioTrack(state.player.audio)
        state.pc.addTrack(monitored_audio)
        logger.info("✅ Audio track added (Camera audio - monitored)")
    else:
        logger.warning("⚠️ No audio available - video call will be video-only")

    # Setup event handlers
    setup_peer_connection_handlers()

def setup_peer_connection_handlers():
    """Thiết lập các event handlers cho peer connection"""
    
    @state.pc.on("connectionstatechange")
    async def on_connectionstatechange():
        state_name = state.pc.connectionState
        emoji = {"new": "🆕", "connecting": "🔄", "connected": "✅", "disconnected": "⚠️", "failed": "❌", "closed": "🔒"}
        logger.info(f"{emoji.get(state_name, '❓')} Connection state: {state_name}")
        
        if state_name == "failed":
            logger.error("❌ WebRTC connection FAILED!")
            logger.error("💡 Troubleshooting tips:")
            logger.error("   1. Check if mobile app has internet connection")
            logger.error("   2. Try using mobile data instead of WiFi (or vice versa)")
            logger.error("   3. Check firewall settings on both devices")
            logger.error("   4. Ensure both devices can reach TURN servers")
            # ⚠️ DISABLE ICE restart to avoid loop - debug first
            # try:
            #     await schedule_ice_restart("connectionstate=failed")
            # except Exception as e:
            #     logger.warning(f"ICE restart attempt failed to schedule: {e}")
        elif state_name == "connected":
            logger.info("🎉 WebRTC connection ESTABLISHED!")
            if state.video_monitor_task is None or state.video_monitor_task.done():
                state.video_monitor_task = asyncio.create_task(monitor_video())
        elif state_name == "disconnected":
            # ⚠️ DISABLE ICE restart to avoid loop
            # try:
            #     await schedule_ice_restart("connectionstate=disconnected")
            # except Exception as e:
            #     logger.warning(f"ICE restart attempt failed to schedule: {e}")
            pass

    @state.pc.on("track")
    async def on_track(track):
        try:
            logger.info(f"📥 Incoming track: kind={track.kind}, id={track.id}")
            if track.kind == "audio":
                await handle_incoming_audio_track(track)
            elif track.kind == "video":
                logger.info("🎥 Incoming video track received")
        except Exception as e:
            logger.error(f"Error in on_track handler: {e}")

    @state.pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        ice_state = state.pc.iceConnectionState
        emoji = {"new": "🆕", "checking": "🔍", "connected": "✅", "completed": "🏁", "failed": "❌", "disconnected": "⚠️", "closed": "🔒"}
        logger.info(f"{emoji.get(ice_state, '❓')} ICE connection state: {ice_state}")
        
        # 🔍 DEBUG: Chi tiết khi ICE failed
        if ice_state == "failed":
            logger.error("")
            logger.error("=" * 70)
            logger.error("🔍 ICE CONNECTION FAILED - PHÂN TÍCH")
            logger.error("=" * 70)
            try:
                # Truy cập internal ICE transport
                sctp = state.pc._RTCPeerConnection__sctp
                if sctp and hasattr(sctp, 'transport') and hasattr(sctp.transport, '_connection'):
                    ice_conn = sctp.transport._connection
                    
                    # Thống kê candidates
                    local_candidates = ice_conn.local_candidates
                    remote_candidates = ice_conn.remote_candidates
                    
                    local_relay = [c for c in local_candidates if c.type == 'relay']
                    remote_relay = [c for c in remote_candidates if c.type == 'relay']
                    
                    logger.error(f"📊 Local Candidates: {len(local_candidates)} total")
                    for c in local_candidates[:5]:
                        logger.error(f"   {c.type.upper()}: {c.host}:{c.port}")
                    
                    logger.error(f"📊 Remote Candidates: {len(remote_candidates)} total")
                    for c in remote_candidates[:5]:
                        logger.error(f"   {c.type.upper()}: {c.host}:{c.port}")
                    
                    if not local_relay:
                        logger.error("")
                        logger.error("❌ KHÔNG CÓ LOCAL RELAY CANDIDATES!")
                        logger.error("   TURN allocation failed hoặc chưa hoàn thành")
                    
                    if not remote_relay:
                        logger.error("")
                        logger.error("❌ KHÔNG CÓ REMOTE RELAY CANDIDATES!")
                        logger.error("   Mobile không gửi RELAY candidates hoặc bị filter")
                    
                    # Phân tích failed pairs
                    logger.error("")
                    logger.error("🔍 Failed Candidate Pairs (top 5):")
                    failed = [p for p in ice_conn.check_list if p.state.name == 'FAILED'][:5]
                    for i, p in enumerate(failed, 1):
                        logger.error(f"   {i}. {p.local_candidate.type}({p.local_candidate.host}:{p.local_candidate.port})")
                        logger.error(f"      -> {p.remote_candidate.type}({p.remote_candidate.host}:{p.remote_candidate.port})")
                    
                    if failed:
                        relay_pairs = [p for p in failed if p.local_candidate.type == 'relay' or p.remote_candidate.type == 'relay']
                        if relay_pairs:
                            logger.error(f"")
                            logger.error(f"⚠️ {len(relay_pairs)} RELAY pairs cũng failed!")
                            logger.error(f"   -> Có thể do firewall chặn TURN traffic")
                        else:
                            logger.error(f"")
                            logger.error(f"💡 Không có RELAY pairs nào được test!")
                            logger.error(f"   -> Thiếu RELAY candidates từ 1 hoặc 2 bên")
                    
            except Exception as e:
                logger.error(f"❌ Không thể phân tích: {e}")
            
            logger.error("=" * 70)
            logger.error("")
        
        # ⚠️ DISABLE ICE restart to avoid loop - debug candidate pairs first
        # if ice_state in ("disconnected", "failed"):
        #     try:
        #         await schedule_ice_restart(f"iceconnectionstate={ice_state}")
        #     except Exception as e:
        #         logger.warning(f"ICE restart attempt failed to schedule: {e}")

    @state.pc.on("icegatheringstatechange")
    async def on_icegatheringstatechange():
        logger.info(f"📡 ICE gathering state: {state.pc.iceGatheringState}")

    @state.pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            cand_str = candidate.candidate

            # ⚠️ CRITICAL: Filter candidates BEFORE publishing when FORCE_TURN is enabled
            try:
                if candidate_from_sdp:
                    parsed = candidate_from_sdp(cand_str)
                    if FORCE_TURN and getattr(parsed, "type", None) != "relay":
                        logger.info(f"⏭️ Not publishing non-RELAY local candidate due to FORCE_TURN: {cand_str[:60]}")
                        return
                    if FORCE_IPV4 and ":" in getattr(parsed, "ip", ""):
                        logger.info("⏭️ Not publishing IPv6 local candidate due to --force-ipv4")
                        return
                else:
                    # Fallback: simple string-based filtering
                    if FORCE_TURN and " typ relay" not in cand_str:
                        logger.info(f"⏭️ Not publishing non-RELAY local candidate due to FORCE_TURN: {cand_str[:60]}")
                        return
                    if FORCE_IPV4 and ":" in cand_str:
                        logger.info("⏭️ Not publishing IPv6 local candidate due to --force-ipv4")
                        return
            except Exception as e:
                logger.warning(f"Candidate filtering error: {e}")
                # If parsing fails and FORCE_TURN is on, skip to be safe
                if FORCE_TURN and " typ relay" not in cand_str:
                    logger.info(f"⏭️ Skipping candidate (parsing failed, FORCE_TURN active): {cand_str[:60]}")
                    return

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
            # Publish candidates to mobile/{DEVICE_ID} so the app receives them
            topic = f"mobile/{DEVICE_ID}/webrtc/candidate"
            state.client.publish(topic, payload)
            logger.info(f"📤 Published ICE candidate to {topic}")
        else:
            logger.info("🏁 ICE candidate gathering complete (end-of-candidates)")

async def start_sos_call():
    """Khởi tạo cuộc gọi từ device"""
    if state.pc and state.pc.connectionState != "closed":
        logger.warning("⚠️ Connection already exists, skipping...")
        return

    logger.info("🆘 Starting SOS call...")
    state.pending_ice_candidates = deque()
    state.last_remote_answer_sdp = None
    await initialize_peer_connection()
    
    if state.pc:
        offer = await state.pc.createOffer()
        await state.pc.setLocalDescription(offer)

        payload = json.dumps({"sdp": offer.sdp, "type": offer.type})
        # When device initiates call, publish offer to mobile/{DEVICE_ID}
        state.client.publish(f"mobile/{DEVICE_ID}/webrtc/offer", payload)
        logger.info("📤 Offer published to MQTT")

async def answer_call():
    """Trả lời cuộc gọi từ mobile"""
    if state.pc:
        if not state.pc.remoteDescription or state.pc.remoteDescription.type != "offer":
            logger.warning(f"⚠️ answer_call invoked but remoteDescription missing/invalid (state={state.pc.signalingState})")
            return
        if state.pc.signalingState != "have-remote-offer":
            if state.pc.signalingState == "stable":
                logger.info("ℹ️ Already stable; skipping answer creation")
                return
            logger.warning(f"⚠️ Cannot create answer in signalingState={state.pc.signalingState}")
            return
        
        answer = await state.pc.createAnswer()
        await state.pc.setLocalDescription(answer)

        payload = json.dumps({"sdp": answer.sdp, "type": answer.type})
        # Device answers should be sent to mobile/{DEVICE_ID}
        state.client.publish(f"mobile/{DEVICE_ID}/webrtc/answer", payload)
        logger.info("📤 Answer published to MQTT")
