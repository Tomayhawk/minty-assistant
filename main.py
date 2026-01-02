import openwakeword
from openwakeword.model import Model
import pyaudio
import numpy as np
from faster_whisper import WhisperModel
import wave
import os
import ollama
import json
import subprocess
import webbrowser
import time
import math
import struct
import shutil
import openwakeword
from openwakeword.model import Model
import pyaudio
import numpy as np
from faster_whisper import WhisperModel
import wave
import os
import ollama
import json
import subprocess
import webbrowser
import time
import math
import struct
import shutil
import requests
import sys
from contextlib import contextmanager

WAKE_WORD_THRESHOLD = 0.2
RECORD_SECONDS = 4
TEMP_FILE = "command.wav"
LLM_MODEL = "llama3.2"

@contextmanager
def ignore_stderr():
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)
    try:
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)

print("Loading Wake Word Model...")
with ignore_stderr():
    ww_model = Model(wakeword_model_paths=["./hey_minty.onnx"])

print(f"Loading Whisper & Connecting to {LLM_MODEL}...")
stt_model = WhisperModel("base.en", device="cpu", compute_type="int8")

def speak(text):
    """
    Uses Piper TTS to generate high-quality audio.
    We pipe the audio directly to 'aplay' for low latency.
    """
    print(f"Minty says: {text}")
    import shlex
    safe_text = shlex.quote(text)
    command = (
        f'echo {safe_text} | '
        f'./piper_tts/piper/piper --model ./piper_tts/en_US-lessac-high.onnx --output-raw | '
        f'aplay -r 22050 -f S16_LE -t raw -'
    )
    subprocess.run(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def analyze_intent(user_text, context=None):
    print(f"Analyzing: {user_text}...")
    system_instruction = """
    You are an Intent Classifier. You do NOT answer questions. You only categorize them.

    Categories:
    - "launch": Open apps (Target = app name)
    - "search": Google search (Target = query)
    - "control": System control (Target = volume/brightness)
    - "time": Ask time
    - "weather": Ask weather
    - "chat": General conversation, jokes, or identity questions.
    - "quit": Stop or exit the assistant.
    - "restart": Restart the assistant (useful for updates).
    - "unknown": If unsure.

    CRITICAL RULE for "chat": 
    If the input is a question like "Who are you?" or "Tell me a joke", the target MUST be the user's EXACT input. 
    Do not generate an answer.

    Output ONLY JSON. 
    Format: {"action": "launch", "target": "firefox", "clarification": null}
    """

    if context and context.get("pending_action"):
        pending = context["pending_action"]
        system_instruction += f"""
        CONTEXT: The user previously asked to {pending['action']} {pending['target']}, but we needed confirmation.
        If the user says 'yes', 'yeah', or confirms, output the pending action exactly.
        If they say 'no', output action: "unknown".
        """

    try:
        response = ollama.chat(model=LLM_MODEL, messages=[
            {'role': 'system', 'content': system_instruction},
            {'role': 'user', 'content': user_text},
        ], format="json")
        return json.loads(response['message']['content'])
    except Exception as e:
        print(f"LLM Error: {e}")
        return {"action": "unknown", "target": None}

def execute_action(intent_data):
    action = intent_data.get("action")
    target = intent_data.get("target")
    clarification = intent_data.get("clarification")
    if target:
        target = target.lower().strip()
    print(f"--> EXECUTING: {action} on {target}")

    if action == "launch":
        custom_commands = {
            "genshin": ["steam", "-silent", "steam://rungameid/12391600296810250240"],
            "genshinimpact": ["steam", "-silent", "steam://rungameid/12391600296810250240"],
            "genshin impact": ["steam", "-silent", "steam://rungameid/12391600296810250240"],
            "honkaistarrail": ["/usr/bin/flatpak", "run", "--branch=stable", "--arch=x86_64", "--command=moe.launcher.the-honkers-railway-launcher", "moe.launcher.the-honkers-railway-launcher"],
            "honkai star rail": ["/usr/bin/flatpak", "run", "--branch=stable", "--arch=x86_64", "--command=moe.launcher.the-honkers-railway-launcher", "moe.launcher.the-honkers-railway-launcher"],
            "monitor": ["gnome-system-monitor"]
        }

        if target in custom_commands:
            speak(f"Launching {target}")
            subprocess.Popen(
                custom_commands[target], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            return "DONE"

        app_path = shutil.which(target)
        if app_path:
            speak(f"Opening {target}")
            subprocess.Popen(
                [app_path], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
        else:
            common_aliases = {"chrome": "google-chrome", "code": "code", "steam": "steam", "files": "nemo",
                "settings": "cinnamon-settings"}
            real_name = common_aliases.get(target, target)
            if shutil.which(real_name):
                 speak(f"Opening {real_name}")
                 subprocess.Popen([real_name])
            else:
                 speak(f"I couldn't find an app named {target}")

    elif action == "search":
        speak(f"Searching Google for {target}")
        url = f"https://www.google.com/search?q={target}"
        webbrowser.open(url)
        
    elif action == "clarification":
        speak(clarification)
        return "WAITING_FOR_CONFIRMATION"

    elif action == "time":
        from datetime import datetime
        now = datetime.now().strftime("%I:%M %p")
        speak(f"It is currently {now}")

    elif action == "control":
        if "volume" in target and "up" in target:
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "10%+"])
            speak("Turning it up.")
        elif "volume" in target and "down" in target:
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "10%-"])
            speak("Turning it down.")
        elif "mute" in target:
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "toggle"])
            speak("Muting audio.")
    
    elif action == "weather":
        try:
            response = requests.get("https://wttr.in/London?format=3") 
            weather_text = response.text.strip()
            speak(f"The current weather is {weather_text}")
        except:
            speak("I couldn't get the weather data right now.")

    elif action == "chat":
        speak("Let me think...")
        persona = """
        You are Minty, a smart and helpful assistant running on Linux Mint.
        Your personality is friendly, concise, and tech-savvy.
        You are talking to the user via voice, so keep your answers short (1-2 sentences) and easy to speak.
        """
        response = ollama.chat(model=LLM_MODEL, messages=[
            {'role': 'system', 'content': persona},
            {'role': 'user', 'content': target}
        ])
        answer = response['message']['content']
        speak(answer)
    elif action == "quit":
        speak("Goodbye!")
        return "QUIT"
        
    elif action == "restart":
        speak("Restarting systems...")
        return "RESTART"
    else:
        speak("I am not sure how to do that yet.")
    
    return "DONE"

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1280

with ignore_stderr():
    audio = pyaudio.PyAudio()

mic_stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, 
                        input=True, frames_per_buffer=CHUNK)

def calculate_rms(audio_data):
    count = len(audio_data) / 2
    format = "%dh" % (count)
    shorts = struct.unpack(format, audio_data)
    sum_squares = 0.0
    for sample in shorts:
        n = sample * (1.0 / 32768.0)
        sum_squares += n * n
    return math.sqrt(sum_squares / count)

def record_until_silence(threshold=0.03, silence_duration=1.5, max_wait_seconds=5):
    print("Listening... (speak now)")
    frames = []
    silence_start_time = None
    has_spoken = False
    start_time = time.time()
    
    while True:
        data = mic_stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)
        rms = calculate_rms(data)
        if rms > threshold:
            has_spoken = True
            silence_start_time = None
        elif has_spoken and rms < threshold:
            if silence_start_time is None:
                silence_start_time = time.time()
            elif time.time() - silence_start_time > silence_duration:
                break
        if not has_spoken and (time.time() - start_time) > max_wait_seconds:
            print("Timeout: No speech detected.")
            return None
        if len(frames) * CHUNK / RATE > 10:
            break

    with wave.open(TEMP_FILE, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
    return TEMP_FILE

def transcribe_audio(file_path):
    segments, info = stt_model.transcribe(
        file_path, beam_size=5, 
        initial_prompt="Linux Mint, Minty, Firefox, launch, terminal, sudo, " \
                        "Genshin, Genshin Impact, HSR, Honkai Star Rail"
    )
    return " ".join([segment.text for segment in segments]).strip()

context = {"pending_action": None}

print("\n--- Minty is READY. Say 'Hey Minty'! ---")

SOUND_WAKE = "/usr/share/sounds/freedesktop/stereo/service-login.oga"
SOUND_SLEEP = "/usr/share/sounds/freedesktop/stereo/service-logout.oga"

try:
    while True:
        data = mic_stream.read(CHUNK, exception_on_overflow=False)
        audio_data = np.frombuffer(data, dtype=np.int16)
        prediction = ww_model.predict(audio_data)

        if prediction["hey_minty"] > 0.1:
            print(f"Confidence: {prediction['hey_minty']}")

        if prediction["hey_minty"] > WAKE_WORD_THRESHOLD:
            if os.path.exists(SOUND_WAKE):
                subprocess.Popen(["paplay", SOUND_WAKE])
            
            print("\nListening...")
            mic_stream.stop_stream()
            mic_stream.start_stream()
            filename = record_until_silence(max_wait_seconds=5)
            if filename is None:
                print("--- Resetting ---")
                mic_stream.stop_stream()
                ww_model.reset()
                if os.path.exists(SOUND_SLEEP):
                    subprocess.run(["paplay", SOUND_SLEEP], stderr=subprocess.DEVNULL)
                mic_stream.start_stream()
                continue

            user_text = transcribe_audio(filename)
            print(f"User said: '{user_text}'")
            
            if user_text:
                try:
                    if mic_stream.is_active():
                        mic_stream.stop_stream()

                    intent = analyze_intent(user_text, context)
                    result = execute_action(intent)
                    
                    if result == "QUIT":
                        print("User requested quit.")
                        sys.exit(0)
                    elif result == "RESTART":
                        print("Restarting...")
                        os.execv(sys.executable, ['python'] + sys.argv)
                    
                    if intent.get("action") not in ["chat", "unknown", "quit", "restart"]:
                        if os.path.exists(SOUND_SLEEP):
                            subprocess.run(["paplay", SOUND_SLEEP], stderr=subprocess.DEVNULL)

                    if result == "WAITING_FOR_CONFIRMATION":
                        context["pending_action"] = {"action": "launch", "target": intent.get("target")}
                    elif result == "DONE":
                        context["pending_action"] = None
                except SystemExit:
                    raise
                except Exception as e:
                    print(f"Error executing action: {e}")
                finally:
                    if not mic_stream.is_active():
                        mic_stream.start_stream()
            
            mic_stream.stop_stream()
            ww_model.reset()

            mic_stream.start_stream()

except KeyboardInterrupt:
    print("\nStopping Minty...")
finally:
    mic_stream.stop_stream()
    mic_stream.close()
    audio.terminate()
    if os.path.exists(TEMP_FILE):
        os.remove(TEMP_FILE)
    mic_stream.close()
