from faster_whisper import WhisperModel
import config

print("Loading Whisper Model...")
stt_model = WhisperModel("base.en", device="cpu", compute_type="int8")

def is_hallucination(text):
    """Detects if Whisper got stuck in a loop."""
    if not text:
        return True

    words = text.split()
    if len(words) == 0:
        return True

    unique_words = set(w.lower().strip(",.!?") for w in words)
    ratio = len(unique_words) / len(words)

    return len(words) > 3 and ratio < 0.4

def transcribe_audio(file_path):
    """Transcribes audio using Whisper and filters hallucinations."""
    segments, _ = stt_model.transcribe(
        file_path, beam_size=5, 
        initial_prompt="Linux Mint, Minty, Firefox, launch, terminal, sudo"
    )

    full_text = " ".join(segment.text for segment in segments).strip()

    if is_hallucination(full_text):
        print(f"Ignored hallucination: '{full_text}'")
        return None

    return full_text
