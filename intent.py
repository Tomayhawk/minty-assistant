import ollama
import json
import config

def analyze_intent(user_text, context=None):
    print(f"Analyzing: {user_text}...")

    system_instruction = """
    You are an Intent Classifier. You do NOT answer questions. You only categorize them.

    Categories:
    - "launch": Open apps (Target = app name)
    - "search": Google search (Target = query)
    - "control": System control (Target = volume/brightness)
    - "smart_home": Control devices (Target = device name + state)
    - "time": Ask time
    - "weather": Ask weather
    - "chat": General conversation, jokes, or identity questions.
    - "snap": Move Firefox/YouTube windows (Target = position)
    - "audio_mode": Switch headphone quality (Target = "music" or "call")
    - "schedule": Add calendar events (Target = "new_event")
    - "cancel": "nevermind", "cancel" (Target = "cancel")
    - "wait": "wait a sec", "hold on" (Target = "wait")
    - "quit": Stop or exit.
    - "restart": Restart the assistant.
    - "unknown": If unsure.

    CRITICAL RULE for "chat": 
    If the input is a question like "Who are you?", target MUST be the user's EXACT input.

    Output ONLY JSON. Format: {"action": "launch", "target": "firefox", "clarification": null}
    """

    if context and context.get("pending_action"):
        pending = context["pending_action"]
        # If we are in a simple confirmation flow (not calendar)
        if isinstance(pending, dict):
            system_instruction += f"""
            CONTEXT: The user previously asked to {pending['action']} {pending['target']}.
            If confirmed, output the pending action. If denied, output action "unknown".
            """

    try:
        response = ollama.chat(model=config.LLM_MODEL, messages=[
            {'role': 'system', 'content': system_instruction},
            {'role': 'user', 'content': user_text},
        ], format="json")
        return json.loads(response['message']['content'])
    except Exception as e:
        print(f"LLM Error: {e}")
        return {"action": "unknown", "target": None}

def extract_event_details(user_text, current_data=None):
    """
    Uses the LLM to merge new user input into the existing event data.
    """
    if current_data is None: current_data = {}
    print(f"Extracting details from: '{user_text}' with context: {current_data}")

    system_instruction = f"""
    You are a Calendar Assistant. Merge new details into the existing JSON.
    Current Data: {json.dumps(current_data)}
    
    Fields to extract:
    - "summary": Title/Event name.
    - "start_time": Natural language time (e.g., "tomorrow at 5pm").
    - "duration": Duration (e.g., "1 hour").
    - "location": Location.
    - "description": Extra notes.
    
    OUTPUT JSON ONLY.
    """
    
    try:
        response = ollama.chat(model=config.LLM_MODEL, messages=[
            {'role': 'system', 'content': system_instruction},
            {'role': 'user', 'content': user_text},
        ], format="json")
        return json.loads(response['message']['content'])
    except Exception as e:
        print(f"Extraction Error: {e}")
        return current_data