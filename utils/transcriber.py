try:
    import audioop
except ImportError:
    try:
        # This looks for the utils/audioop_copy.py file in the same directory
        from . import audioop_copy as audioop
        import sys
        sys.modules['audioop'] = audioop
    except ImportError:
        # Fallback for different directory structures
        import audioop_copy as audioop
        import sys
        sys.modules['audioop'] = audioop

import os
import gc
import threading
import queue
import time
import subprocess
from groq import Groq

# We still import pydub just in case, but we avoid using it for the main conversion
# to save memory on the Render Free Tier.
try:
    from pydub import AudioSegment
except ImportError:
    pass

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def convert_to_mp3(input_path):
    """
    Memory-efficient conversion using FFmpeg streaming.
    This prevents 'Connection Reset' errors on Render by not loading 
    the audio into RAM.
    """
    try:
        mp3_path = input_path.rsplit('.', 1)[0] + "_converted.mp3"
        
        # FFmpeg command: Mono, 16000Hz, 32k bitrate (Highly compressed for Groq)
        command = [
            'ffmpeg', '-y', '-i', input_path,
            '-ac', '1',                # Mono
            '-ar', '16000',            # 16kHz sample rate
            '-b:a', '32k',             # 32kbps bitrate
            mp3_path
        ]
        
        # Run the conversion as a background system process
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return mp3_path
    except Exception as e:
        print(f"Streaming Conversion Error: {e}")
        # If FFmpeg fails, we return the original path as a fallback
        return input_path  

def transcribe_audio_stream(file_path):
    gc.collect()
    result_queue = queue.Queue()

    # --- STEP 1: UNIVERSAL CONVERSION ---
    yield ">>> PRE-PROCESSING AUDIO FOR UNIVERSAL SUPPORT...", None
    
    # We use the new streaming converter to keep RAM usage near zero
    final_file_to_send = convert_to_mp3(file_path)
    
    # Use a clean metadata name to avoid Groq 400 errors
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

    # Start Groq Thread
    thread = threading.Thread(target=perform_transcription)
    thread.daemon = True
    thread.start()

    # --- STEP 2: HEARTBEAT ---
    while thread.is_alive():
        yield "AI Professor is listening to the lecture...", None
        thread.join(timeout=2.0) 

    status, data = result_queue.get()

    # Cleanup the temporary MP3 file
    if final_file_to_send != file_path and os.path.exists(final_file_to_send):
        try:
            os.remove(final_file_to_send)
        except:
            pass

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
            time.sleep(0.04) # Simulated live typing effect

    yield None, "\n".join(full_transcript)
    gc.collect()