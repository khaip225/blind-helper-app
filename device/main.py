"""
WebRTC Video Call Simulator - Main Entry Point
"""
import asyncio
import sys
import threading
import argparse
import os
from config import (
    logger, state, DEVICE_ID, MQTT_BROKER, MQTT_PORT,
    FORCE_TURN, FORCE_IPV4, TURN_URLS, TURN_USERNAME, TURN_PASSWORD,
    PLAYBACK_GAIN, PLAYBACK_OUTPUT_RATE
)
from utils import print_banner
from mqtt_handler import setup_mqtt_client
from webrtc_handler import start_sos_call

async def main():
    """Main function"""
    # Setup audio devices first (unmute and set volume)
    import platform
    import subprocess
    if platform.system() == "Linux":
        try:
            setup_script = os.path.join(os.path.dirname(__file__), "setup_audio.sh")
            if os.path.exists(setup_script):
                subprocess.run([setup_script], check=False, capture_output=True)
                logger.info("🔊 Audio devices configured")
        except Exception as e:
            logger.warning(f"Could not run audio setup script: {e}")
    
    # Parse CLI arguments
    parser = argparse.ArgumentParser(description="WebRTC Video Call Simulator")
    parser.add_argument("--device-id", default=os.environ.get("DEVICE_ID", DEVICE_ID))
    parser.add_argument("--force-turn", action="store_true", default=FORCE_TURN)
    parser.add_argument("--force-ipv4", action="store_true", default=FORCE_IPV4)
    parser.add_argument("--turn-urls", default=",".join(TURN_URLS))
    parser.add_argument("--turn-username", default=TURN_USERNAME)
    parser.add_argument("--turn-password", default=TURN_PASSWORD)
    parser.add_argument("--playback-gain", type=float, default=PLAYBACK_GAIN)
    parser.add_argument("--playback-rate", type=int, default=PLAYBACK_OUTPUT_RATE)
    args = parser.parse_args()

    # Update configuration from CLI args
    import config as cfg
    cfg.DEVICE_ID = args.device_id
    cfg.FORCE_TURN = bool(args.force_turn)
    cfg.FORCE_IPV4 = bool(args.force_ipv4)
    cfg.TURN_URLS = [u.strip() for u in args.turn_urls.split(",") if u.strip()] if args.turn_urls else []
    cfg.TURN_USERNAME = args.turn_username
    cfg.TURN_PASSWORD = args.turn_password
    cfg.PLAYBACK_GAIN = max(0.1, min(args.playback_gain, 10.0))
    cfg.PLAYBACK_OUTPUT_RATE = int(args.playback_rate)

    # Update imports to use updated config
    import webrtc_handler
    import mqtt_handler
    webrtc_handler.DEVICE_ID = cfg.DEVICE_ID
    webrtc_handler.FORCE_TURN = cfg.FORCE_TURN
    webrtc_handler.FORCE_IPV4 = cfg.FORCE_IPV4
    webrtc_handler.TURN_URLS = cfg.TURN_URLS
    webrtc_handler.TURN_USERNAME = cfg.TURN_USERNAME
    webrtc_handler.TURN_PASSWORD = cfg.TURN_PASSWORD
    webrtc_handler.ICE_RESTART_COOLDOWN = cfg.ICE_RESTART_COOLDOWN
    
    import audio_handler
    audio_handler.PLAYBACK_GAIN = cfg.PLAYBACK_GAIN
    audio_handler.PLAYBACK_OUTPUT_RATE = cfg.PLAYBACK_OUTPUT_RATE

    # Print startup banner
    print_banner(
        args.device_id,
        MQTT_BROKER,
        MQTT_PORT,
        args.force_turn,
        args.force_ipv4,
        [u.strip() for u in args.turn_urls.split(",") if u.strip()] if args.turn_urls else [],
        args.turn_username,
        args.turn_password,
        args.playback_gain,
        args.playback_rate
    )
    
    # Setup MQTT client
    state.client = setup_mqtt_client()
    logger.info("🔌 Connecting to MQTT broker...")
    state.client.connect(MQTT_BROKER, MQTT_PORT, 60)

    state.main_loop = asyncio.get_running_loop()
    state.client.loop_start()

    # Setup user input handler
    sos_requested = asyncio.Event()

    def user_input_handler():
        while True:
            try:
                sys.stdin.readline()
                state.main_loop.call_soon_threadsafe(sos_requested.set)
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
        
        # Cleanup
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
        
        if state.pyaudio_track is not None:
            try:
                state.pyaudio_track.stop()
            except Exception:
                pass
        
        if state.playback_task is not None:
            try:
                state.playback_task.cancel()
            except Exception:
                pass
        
        if state._pyaudio_out_stream is not None:
            try:
                state._pyaudio_out_stream.stop_stream()
                state._pyaudio_out_stream.close()
            except Exception:
                pass
        
        if state._pyaudio_out is not None:
            try:
                state._pyaudio_out.terminate()
            except Exception:
                pass
        
        if state.recorder:
            try:
                await state.recorder.stop()
            except Exception:
                pass
        
        if state.pc:
            await state.pc.close()
        
        state.client.loop_stop()
        state.client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Simulator stopped by user.")
