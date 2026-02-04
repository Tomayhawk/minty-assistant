import pyaudio, wave, math, struct, time, subprocess, shlex, os, sys
import numpy as np
from faster_whisper import WhisperModel
from contextlib import contextmanager
import config

@contextmanager
def ignore_stderr():
    devnull = os.open(os.devnull, os.O_WRONLY)
    old = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)
    try: yield
    finally: os.dup2(old, 2); os.close(old)

class IOEngine:
    def __init__(self):
        with ignore_stderr():
            self.pa = pyaudio.PyAudio()
            self.stt = WhisperModel("base.en", device="cpu", compute_type="int8")
        self.stream = self.pa.open(format=pyaudio.paInt16, channels=1, rate=config.RATE, input=True, frames_per_buffer=config.CHUNK)

    def speak(self, text):
        print(f"🤖 {text}")
        subprocess.run(config.TTS_CMD.format(text=shlex.quote(text)), shell=True, stderr=subprocess.DEVNULL)

    def play_sound(self, path):
        if os.path.exists(path): subprocess.Popen(["paplay", path], stderr=subprocess.DEVNULL)

    def listen(self, threshold=0.01, timeout=5):
        print(f"🎤 Listening...")
        frames, silence_start, has_spoken = [], None, False
        start_t = time.time()

        while True:
            data = self.stream.read(config.CHUNK, exception_on_overflow=False)
            frames.append(data)
            rms = math.sqrt(sum((s/32768.0)**2 for s in struct.unpack(f"%dh"%(len(data)/2), data)) / (len(data)/2))

            if rms > threshold: has_spoken, silence_start = True, None
            elif has_spoken and rms < threshold:
                if not silence_start: silence_start = time.time()
                elif time.time() - silence_start > 1.2: break
            
            if (time.time() - start_t) > timeout and not has_spoken: return None

        with wave.open(config.TEMP_AUDIO, 'wb') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(config.RATE)
            wf.writeframes(b''.join(frames))
        return config.TEMP_AUDIO

    def transcribe(self, audio_path):
        segments, _ = self.stt.transcribe(audio_path, beam_size=5, initial_prompt="Linux, Minty, sudo, apt")
        text = " ".join(s.text for s in segments).strip()
        # Simple Hallucination Filter
        if len(text.split()) > 4 and len(set(text.split())) / len(text.split()) < 0.4: return None
        return text

    def cleanup(self):
        self.stream.stop_stream(); self.stream.close(); self.pa.terminate()
