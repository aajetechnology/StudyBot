import os 
import gc
from faster_whisper import WhisperModel


# NEW: Generator function for the LIVE LOGS
def transcribe_audio_stream(file_path):
    gc.collect()
    print("Starting transcription ...", flush=True)
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, info = model.transcribe(file_path, beam_size=1, condition_on_previous_text=False)
    print(f"Detected langusage: {info.language}", flush=True)

    full_transcript = []
    for segment in segments:
        print(f"[log] Transcribing: {segment.text}", flush=True)
        timestamp = f"[{int(segment.start // 60):02}:{int(segment.start % 60):02}] "
        line = f"{timestamp} {segment.text.strip()}"
        print(f"DEBUG: {line}")
        full_transcript.append(line)
        
        yield line, None 
    
    del model
    gc.collect()
        
    
    yield None, "\n".join(full_transcript)