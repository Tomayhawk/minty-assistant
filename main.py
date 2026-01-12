import numpy as np
import subprocess
import os
import sys
from openwakeword.model import Model

# Import our custom modules
import config
import audio
import transcription
import intent
import actions
from utils import ignore_stderr

# --- 1. Load Models ---
print("Loading Wake Word Model...")
with ignore_stderr():
    ww_model = Model(wakeword_model_paths=["./hey_minty.onnx"])

# --- 2. Initialize State ---
context = {"pending_action": None}
skip_wake_word = False       
listen_timeout = 5           
noise_retry_count = 0        

print("\n--- Minty is READY. Say 'Hey Minty'! ---")

try:
    while True:
        # --- 3. READ AUDIO & WAKE WORD ---
        data = audio.mic_stream.read(config.CHUNK, exception_on_overflow=False)
        
        if skip_wake_word:
            confidence = 1.0
            print("--> Bypassing Wake Word (Waiting for user input...)")
            skip_wake_word = False
        else:
            audio_data = np.frombuffer(data, dtype=np.int16)
            prediction = ww_model.predict(audio_data)
            confidence = prediction["hey_minty"]

        # --- 4. IF TRIGGERED ---
        if confidence > config.WAKE_WORD_THRESHOLD:
            
            # Play beep only on fresh Wake Word (not internal retries)
            if listen_timeout == 5 and os.path.exists(config.SOUND_WAKE):
                subprocess.Popen(["paplay", config.SOUND_WAKE])
            
            print(f"\nListening... (Timeout: {listen_timeout}s)")
            
            audio.mic_stream.stop_stream()
            audio.mic_stream.start_stream()
            
            # Record
            filename = audio.record_until_silence(max_wait_seconds=listen_timeout)

            # --- 5. HANDLE TIMEOUT (Silence) ---
            if filename is None:
                print("--- Resetting ---")
                if os.path.exists(config.SOUND_SLEEP):
                     subprocess.run(["paplay", config.SOUND_SLEEP], stderr=subprocess.DEVNULL)
                
                audio.mic_stream.stop_stream()
                ww_model.reset()
                audio.mic_stream.start_stream()
                continue

            # --- 6. TRANSCRIBE ---
            user_text = transcription.transcribe_audio(filename)
            
            # --- 7. HANDLE NOISE / HALLUCINATIONS ---
            if not user_text:
                noise_retry_count += 1
                if noise_retry_count < 3:
                    print(f"--> Noise detected ({noise_retry_count}/3). Retrying silently...")
                    skip_wake_word = True   # Bypass wake word
                    # Do NOT reset listen_timeout here (keeps the 20s wait if active)
                    
                    audio.mic_stream.stop_stream()
                    ww_model.reset()
                    audio.mic_stream.start_stream()
                    continue
                else:
                    print("--> Too much noise. Resetting to Idle.")
                    noise_retry_count = 0
                    skip_wake_word = False
                    listen_timeout = 5 # Reset timeout
                    
                    if os.path.exists(config.SOUND_SLEEP):
                        subprocess.run(["paplay", config.SOUND_SLEEP], stderr=subprocess.DEVNULL)
                    
                    audio.mic_stream.stop_stream()
                    ww_model.reset()
                    audio.mic_stream.start_stream()
                    continue
            
            # --- 8. EXECUTE ACTION ---
            noise_retry_count = 0
            print(f"User said: '{user_text}'")

            if user_text:
                try:
                    if audio.mic_stream.is_active():
                        audio.mic_stream.stop_stream()

                    # ROUTING LOGIC: Calendar vs Standard Intent
                    if context.get("pending_action") == "calendar_flow":
                        result = actions.handle_calendar_conversation(user_text, context)
                    else:
                        intent_data = intent.analyze_intent(user_text, context)
                        result = actions.execute_action(intent_data)
                    
                    # Reset timeout to default (5s) unless Action requests Extension
                    listen_timeout = 5

                    # --- RESULT HANDLING ---
                    if result == "EXTENDED_LISTEN":
                        skip_wake_word = True
                        listen_timeout = 20    # "Wait a sec"
                        
                    elif result == "WAITING_FOR_CALENDAR":
                        context["pending_action"] = "calendar_flow"
                        skip_wake_word = True
                        listen_timeout = 10    # Give time to answer "What time?"
                    
                    elif result == "WAITING_FOR_CONFIRMATION":
                        context["pending_action"] = {"action": "launch", "target": intent_data.get("target")}
                    
                    elif result == "DONE":
                        context["pending_action"] = None
                        context["event_data"] = {} 
                        
                    elif result == "QUIT":
                        print("User requested quit.")
                        sys.exit(0)
                        
                    elif result == "RESTART":
                        print("Restarting...")
                        os.execv(sys.executable, ['python'] + sys.argv)
                    
                    elif result == "WAITING_FOR_CONFIRMATION":
                        context["pending_action"] = {
                            "action": intent_data.get("action"), 
                            "target": intent_data.get("target"),
                            "confirmed": True
                        }

                        skip_wake_word = True 
                        listen_timeout = 8
                        
                    # Play Success Sound (only if transaction finished)
                    if result == "DONE" or result == "WAITING_FOR_CONFIRMATION":
                         if os.path.exists(config.SOUND_SLEEP):
                            subprocess.run(["paplay", config.SOUND_SLEEP], stderr=subprocess.DEVNULL)

                except SystemExit:
                    raise
                except Exception as e:
                    print(f"Error executing action: {e}")
                finally:
                    if not audio.mic_stream.is_active():
                        audio.mic_stream.start_stream()

            # Reset Model for next turn
            audio.mic_stream.stop_stream()
            ww_model.reset()
            audio.mic_stream.start_stream()

except KeyboardInterrupt:
    print("\nStopping Minty...")
finally:
    audio.cleanup()
    if os.path.exists(config.TEMP_FILE):
        os.remove(config.TEMP_FILE)
