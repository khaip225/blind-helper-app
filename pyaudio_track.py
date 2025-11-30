"""
Custom audio track using PyAudio for Windows microphone capture.
This provides a more reliable alternative to DirectShow MediaPlayer.
"""
import asyncio
import logging
import pyaudio
import struct
from av import AudioFrame
from aiortc import MediaStreamTrack

logger = logging.getLogger("pyaudio_track")

class PyAudioTrack(MediaStreamTrack):
    """
    Audio track that captures audio from the default microphone using PyAudio.
    Works more reliably on Windows than DirectShow.
    """
    
    kind = "audio"
    
    def __init__(self, sample_rate=48000, channels=1, chunk_size=960):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        
        # Initialize PyAudio
        self.audio = pyaudio.PyAudio()
        
        # Try to find default input device
        try:
            default_device = self.audio.get_default_input_device_info()
            logger.info(f"🎤 Default microphone: {default_device['name']}")
            device_index = default_device['index']
        except Exception as e:
            logger.warning(f"Could not get default device: {e}, using device 0")
            device_index = 0
        
        # Open audio stream
        try:
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk_size,
            )
            logger.info(f"✅ PyAudio stream opened: {sample_rate}Hz, {channels} channel(s)")
        except Exception as e:
            logger.error(f"❌ Failed to open PyAudio stream: {e}")
            self.stream = None
    
    async def recv(self):
        """
        Read audio data from microphone and return as AudioFrame.
        """
        if not self.stream:
            # Return silence if no stream
            await asyncio.sleep(0.02)
            return self._silence_frame()
        
        try:
            # Read audio data (blocking, but we'll run in executor)
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self._read_audio)
            
            if not data:
                return self._silence_frame()
            
            # Convert to AudioFrame
            frame = AudioFrame(format='s16', layout='mono' if self.channels == 1 else 'stereo', samples=self.chunk_size)
            frame.sample_rate = self.sample_rate
            frame.pts = self._timestamp
            frame.time_base = self._time_base
            
            # Copy audio data to frame
            frame.planes[0].update(data)
            
            self._timestamp += self.chunk_size
            return frame
            
        except Exception as e:
            logger.error(f"Error reading audio: {e}")
            await asyncio.sleep(0.02)
            return self._silence_frame()
    
    def _read_audio(self):
        """Read audio data from stream (blocking)"""
        try:
            return self.stream.read(self.chunk_size, exception_on_overflow=False)
        except Exception as e:
            logger.warning(f"Audio read error: {e}")
            return None
    
    def _silence_frame(self):
        """Generate a silent audio frame"""
        frame = AudioFrame(format='s16', layout='mono' if self.channels == 1 else 'stereo', samples=self.chunk_size)
        frame.sample_rate = self.sample_rate
        frame.pts = self._timestamp
        frame.time_base = self._time_base
        
        # Fill with silence (zeros)
        silence = b'\x00' * (self.chunk_size * 2 * self.channels)
        frame.planes[0].update(silence)
        
        self._timestamp += self.chunk_size
        return frame
    
    def stop(self):
        """Stop the audio stream"""
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.warning(f"Error stopping stream: {e}")
        
        if self.audio:
            try:
                self.audio.terminate()
            except Exception as e:
                logger.warning(f"Error terminating PyAudio: {e}")
        
        super().stop()
    
    @property
    def _timestamp(self):
        """Get current timestamp"""
        if not hasattr(self, '__timestamp'):
            self.__timestamp = 0
        return self.__timestamp
    
    @_timestamp.setter
    def _timestamp(self, value):
        self.__timestamp = value
    
    @property
    def _time_base(self):
        """Get time base for timestamp"""
        from fractions import Fraction
        return Fraction(1, self.sample_rate)


def list_audio_devices():
    """List all available audio input devices"""
    audio = pyaudio.PyAudio()
    
    print("\n🎤 Available Audio Input Devices:")
    print("=" * 60)
    
    for i in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            is_default = " (DEFAULT)" if i == audio.get_default_input_device_info()['index'] else ""
            print(f"[{i}] {info['name']}{is_default}")
            print(f"    Channels: {info['maxInputChannels']}, Sample Rate: {int(info['defaultSampleRate'])}Hz")
    
    print("=" * 60 + "\n")
    audio.terminate()


if __name__ == "__main__":
    # Test the audio track
    logging.basicConfig(level=logging.INFO)
    list_audio_devices()
