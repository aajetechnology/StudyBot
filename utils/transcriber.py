import os
import gc
import threading
import queue
import time
from groq import Groq
from pydub import AudioSegment

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def convert_to_mp3(input_path):
    """Converts any audio file to a standard MP3 for Groq compatibility."""
    try:
        # Load whatever the user uploaded (m4a, wav, aac, etc.)
        audio = AudioSegment.from_file(input_path)
        
        # Create a path for the new temporary MP3
        mp3_path = input_path.rsplit('.', 1)[0] + "_converted.mp3"
        
        # Export as standard MP3
        audio.export(mp3_path, format="mp3", bitrate="128k")
        return mp3_path
    except Exception as e:
        print(f"Conversion Error: {e}")
        return input_path # Fallback to original if conversion fails

def transcribe_audio_stream(file_path):
    gc.collect()
    result_queue = queue.Queue()

    # --- STEP 1: UNIVERSAL CONVERSION ---
    yield ">>> PRE-PROCESSING AUDIO FOR UNIVERSAL SUPPORT...", None
    final_file_to_send = convert_to_mp3(file_path)
    
    # Use a clean metadata name to avoid the 400 error
    safe_name = "lecture_audio.mp3"

    def perform_transcription():
        try:
            with open(final_file_to_send, "rb") as file:
                transcription = client.audio.transcriptions.create(
                    file=(safe_name, file), 
                    model="whisper-large-v3-turbo",
                    response_format="verbose_json",
                )
            result_queue.put(("SUCCESS", transcription))
        except Exception as e:
            result_queue.put(("ERROR", str(e)))

    # Start Groq
    thread = threading.Thread(target=perform_transcription)
    thread.daemon = True
    thread.start()

    # --- STEP 2: HEARTBEAT ---
    while thread.is_alive():
        yield "AI Professor is listening to the lecture...", None
        thread.join(timeout=2.0) 

    status, data = result_queue.get()

    # Cleanup the temporary MP3 file if we created one
    if final_file_to_send != file_path and os.path.exists(final_file_to_send):
        os.remove(final_file_to_send)

    if status == "ERROR":
        yield f"❌ Groq API Error: {data}", None
        return

    # --- STEP 3: THE SCROLLING TEXT ---
    full_transcript = []
    segments = getattr(data, 'segments', [])
    for segment in segments:
        text = segment.get('text', '') if isinstance(segment, dict) else getattr(segment, 'text', '')
        start = segment.get('start', 0) if isinstance(segment, dict) else getattr(segment, 'start', 0)
        
        if text.strip():
            timestamp = f"[{int(start // 60):02}:{int(start % 60):02}]"
            line = f"{timestamp} {text.strip()}"
            yield line, None
            full_transcript.append(line)
            time.sleep(0.04) # Simulate live typing

    yield None, "\n".join(full_transcript)
    gc.collect()