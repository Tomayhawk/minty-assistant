import subprocess
import shutil
import webbrowser
import requests
import sys
import os
import ollama
import asyncio
import json
import pickle
import datetime
import dateparser
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from kasa import Discover, Credentials

import config
import intent
from audio import speak

def execute_action(intent_data):
    action = intent_data.get("action")
    target = intent_data.get("target")
    clarification = intent_data.get("clarification")
    
    if target:
        target = target.lower().strip()
    
    print(f"--> EXECUTING: {action} on {target}")

    # --- APP LAUNCHING ---
    if action == "launch":
        custom_commands = {
            "genshin": ["steam", "-silent", "steam://rungameid/12391600296810250240"],
            "hsr": ["/usr/bin/flatpak", "run", "--branch=stable", "--arch=x86_64", "--command=moe.launcher.the-honkers-railway-launcher", "moe.launcher.the-honkers-railway-launcher"],
            "monitor": ["gnome-system-monitor"]
        }
        # Handle custom aliases (e.g., "genshin impact" -> "genshin")
        if "genshin" in target: target = "genshin"
        if "star rail" in target: target = "hsr"

        if target in custom_commands:
            speak(f"Launching {target}")
            subprocess.Popen(custom_commands[target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "DONE"

        app_path = shutil.which(target)
        if not app_path:
            # Fallback for common linux names
            aliases = {"chrome": "google-chrome", "code": "code", "steam": "steam", "files": "nemo", "settings": "cinnamon-settings"}
            target = aliases.get(target, target)
            app_path = shutil.which(target)

        if app_path:
            speak(f"Opening {target}")
            subprocess.Popen([app_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            speak(f"I couldn't find an app named {target}")

    # --- WEB & UTILS ---
    elif action == "search":
        speak(f"Searching Google for {target}")
        webbrowser.open(f"https://www.google.com/search?q={target}")

    elif action == "time":
        speak(f"It is currently {datetime.datetime.now().strftime('%I:%M %p')}")

    elif action == "weather":
        try:
            response = requests.get("https://wttr.in/London?format=3") 
            speak(f"The current weather is {response.text.strip()}")
        except:
            speak("I couldn't get the weather data.")

    # --- SYSTEM CONTROL ---
    elif action == "control":
        if "volume" in target:
            if "up" in target:
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "10%+"])
                speak("Turning it up.")
            elif "down" in target:
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "10%-"])
                speak("Turning it down.")
        elif "mute" in target:
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "toggle"])
            speak("Muting audio.")

    elif action == "audio_mode":
        card = config.HEADSET_CARD_ID
        if any(x in target for x in ["music", "quality", "fidelity"]):
            speak("Switching to Music mode.")
            subprocess.run(["pactl", "set-card-profile", card, config.PROFILE_MUSIC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif any(x in target for x in ["call", "headset", "mic"]):
            speak("Switching to Call mode.")
            subprocess.run(["pactl", "set-card-profile", card, config.PROFILE_CALL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            speak("I didn't understand the mode.")

    elif action == "snap":
        trigger_window_snap(target)

    # --- SMART HOME ---
    elif action == "smart_home":
        state = "on" if "on" in target else "off" if "off" in target else None
        if not state:
            speak("I wasn't sure if you wanted it on or off.")
            return "DONE"

        matched_ip = None
        for name, ip in config.KASA_DEVICES.items():
            if name in target:
                matched_ip = ip
                break
        
        if matched_ip:
            speak(f"Turning {state} the device.")
            toggle_kasa_plug(matched_ip, state)
        else:
            speak("I don't see that device in my configuration.")

    # --- CALENDAR ---
    elif action == "schedule":
        # Start the conversation flow
        return handle_calendar_conversation(None, {})

    # --- CONVERSATION & FLOW ---
    elif action == "chat":
        speak("Let me think...")
        persona = "You are Minty, a helpful Linux Assistant. Keep answers concise (1-2 sentences)."
        response = ollama.chat(model=config.LLM_MODEL, messages=[
            {'role': 'system', 'content': persona},
            {'role': 'user', 'content': target}
        ])
        speak(response['message']['content'])
    
    # --- SYSTEM POWER (With Confirmation) ---
    elif action == "system_power":
        if intent_data.get("confirmed"):
            if "re" in target:
                speak("Rebooting system now.")
                subprocess.run(["systemctl", "reboot"])
                return "QUIT"
            elif "shut" in target or "off" in target:
                speak("Shutting down system.")
                subprocess.run(["systemctl", "poweroff"])
                return "QUIT"
        else:
            speak(f"Are you sure you want to {target} the computer?")
            return "WAITING_FOR_CONFIRMATION"

    # --- BLUETOOTH CONNECT ---
    elif action == "bluetooth":
        device_mac = None
        for name, mac in config.BLUETOOTH_DEVICES.items():
            if name in target:
                device_mac = mac
                break
        
        if device_mac:
            speak(f"Connecting to {target}...")
            subprocess.Popen(
                ["bluetoothctl", "connect", device_mac],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            speak(f"I don't have a MAC address saved for {target}.")

    elif action == "clarification":
        speak(clarification)
        return "WAITING_FOR_CONFIRMATION"

    elif action == "cancel":
        speak("Okay, nevermind.")
        return "DONE"

    elif action == "wait":
        speak("Okay, take your time.") 
        return "EXTENDED_LISTEN"

    elif action == "quit":
        speak("Goodbye!")
        return "QUIT"
        
    elif action == "restart":
        speak("Restarting systems...")
        return "RESTART"
    
    return "DONE"

# --- HELPER FUNCTIONS ---

def trigger_window_snap(command_type):
    commands = {
        "bottom_right": "http://cmd/snap-bottom-right",
        "bottom_left":  "http://cmd/snap-bottom-left",
        "native_right": "http://cmd/snap-native",
        "detach":       "http://cmd/detach-snap-right"
    }
    key = command_type.replace(" ", "_").lower()
    url = commands.get(key)
    
    if url:
        speak(f"Snapping window to {key.replace('_', ' ')}.")
        subprocess.Popen(["firefox", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        speak(f"Unknown position {command_type}.")

def toggle_kasa_plug(device_ip, state):
    async def _async_toggle():
        try:
            creds = Credentials(config.KASA_EMAIL, config.KASA_PASSWORD)
            dev = await Discover.discover_single(device_ip, credentials=creds)
            if state == "on": await dev.turn_on()
            else: await dev.turn_off()
        except Exception as e:
            print(f"Kasa Error: {e}")
            speak("I couldn't connect to the device.")
    try:
        asyncio.run(_async_toggle())
    except Exception:
        pass

# --- GOOGLE CALENDAR FUNCTIONS ---

def get_calendar_service():
    creds = None
    if os.path.exists(config.CALENDAR_TOKEN):
        with open(config.CALENDAR_TOKEN, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(config.CALENDAR_CREDENTIALS, config.SCOPES)
            creds = flow.run_local_server(port=0)
        with open(config.CALENDAR_TOKEN, 'wb') as token:
            pickle.dump(creds, token)

    return build('calendar', 'v3', credentials=creds)

def handle_calendar_conversation(user_text, context):
    event_data = context.get("event_data", {})
    
    # Merge new info (skip if first turn and no text)
    if user_text:
        event_data = intent.extract_event_details(user_text, event_data)
    
    # Check for missing fields
    missing = []
    if not event_data.get("summary"): missing.append("title")
    if not event_data.get("start_time"): missing.append("time")
    
    if missing:
        context["event_data"] = event_data
        if "title" in missing: speak("What is the title of the event?")
        elif "time" in missing: speak(f"When is '{event_data.get('summary')}' taking place?")
        return "WAITING_FOR_CALENDAR"

    speak("Adding event to Google Calendar...")
    return create_google_event(event_data)

def create_google_event(data):
    try:
        service = get_calendar_service()
        start_dt = dateparser.parse(data["start_time"])
        if not start_dt: start_dt = datetime.datetime.now() + datetime.timedelta(days=1)
        
        duration_mins = 60
        if data.get("duration"):
            if "30" in data["duration"]: duration_mins = 30
            elif "2" in data["duration"]: duration_mins = 120

        end_dt = start_dt + datetime.timedelta(minutes=duration_mins)

        event_body = {
            'summary': data.get("summary"),
            'location': data.get("location", ""),
            'description': data.get("description", "Added via Minty"),
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'America/Los_Angeles'}, # Update Timezone
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'America/Los_Angeles'},
        }

        service.events().insert(calendarId='primary', body=event_body).execute()
        speak(f"Okay, scheduled {data['summary']} for {start_dt.strftime('%A at %I:%M %p')}.")
        return "DONE"
    except Exception as e:
        print(f"Calendar Error: {e}")
        speak("I had trouble connecting to Google Calendar.")
        return "DONE"
