import pyaudio
import wave
import math
import struct
import time
import subprocess
import shlex
import os
from utils import ignore_stderr
import config

# Initialize PyAudio
with ignore_stderr():
    p = pyaudio.PyAudio()

# Exported mic stream for main.py
mic_stream = p.open(
    format=pyaudio.paInt16, 
    channels=config.CHANNELS, 
    rate=config.RATE, 
    input=True, 
    frames_per_buffer=config.CHUNK
)

def speak(text):
    """Uses Piper TTS to generate audio and pipes it to aplay."""
    print(f"Minty says: {text}")
    safe_text = shlex.quote(text)
    command = (
        f'echo {safe_text} | '
        f'./piper_tts/piper/piper --model ./piper_tts/en_US-lessac-high.onnx --output-raw | '
        f'aplay -r 22050 -f S16_LE -t raw -'
    )
    subprocess.run(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def calculate_rms(audio_data):
    count = len(audio_data) / 2
    format = f"%dh" % count
    shorts = struct.unpack(format, audio_data)
    sum_squares = sum((sample * (1.0 / 32768.0)) ** 2 for sample in shorts)
    return math.sqrt(sum_squares / count)

def record_until_silence(threshold=0.01, silence_duration=1.5, max_wait_seconds=5):
    """Records audio until silence is detected or timeout occurs."""
    print(f"Listening... (Threshold: {threshold})")
    frames = []
    silence_start_time = None
    has_spoken = False
    start_time = time.time()

    while True:
        data = mic_stream.read(config.CHUNK, exception_on_overflow=False)
        frames.append(data)
        rms = calculate_rms(data)

        if rms > threshold:
            if not has_spoken:
                print("Speech detected!")
            has_spoken = True
            silence_start_time = None
        elif has_spoken and rms < threshold:
            if silence_start_time is None:
                silence_start_time = time.time()
            elif time.time() - silence_start_time > silence_duration:
                break

        if not has_spoken and (time.time() - start_time) > max_wait_seconds:
            print(f"Timeout: Max volume was {rms:.4f} (Threshold needed: {threshold})")
            return None

        if len(frames) * config.CHUNK / config.RATE > 10:
            break

    with wave.open(config.TEMP_FILE, 'wb') as wf:
        wf.setnchannels(config.CHANNELS)
        wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(config.RATE)
        wf.writeframes(b''.join(frames))

    return config.TEMP_FILE

def cleanup():
    """Stops the stream and terminates PyAudio to avoid errors on exit."""
    try:
        mic_stream.stop_stream()
        mic_stream.close()
    except Exception:
        pass
    p.terminate()
