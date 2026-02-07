try:
    import audioop
except ImportError:
    try:
        # This looks for the utils/audioop_copy.py file we just made
        from . import audioop_copy as audioop
        import sys
        sys.modules['audioop'] = audioop
    except ImportError:
        import audioop_copy as audioop
        import sys
        sys.modules['audioop'] = audioop

        
import os
import gc
import threading
import queue
import time
from groq import Groq
from pydub import AudioSegment

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def convert_to_mp3(input_path):
    try:
        audio = AudioSegment.from_file(input_path)
        # Convert to Mono and lower sample rate to save massive space
        audio = audio.set_channels(1).set_frame_rate(16000)
        
        mp3_path = input_path.rsplit('.', 1)[0] + "_converted.mp3"
        
        # Export at a very low bitrate (32k is fine for voice)
        audio.export(mp3_path, format="mp3", bitrate="32k")
        return mp3_path
    except Exception as e:
        print(f"Conversion Error: {e}")
        return input_path  
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