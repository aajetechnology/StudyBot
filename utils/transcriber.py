import os
import gc
import threading
import queue
import time
import subprocess
import json
from groq import Groq

# Full paths for reliability on Windows
FFMPEG_PATH = r"C:\Users\Prince Code\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
FFPROBE_PATH = r"C:\Users\Prince Code\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffprobe.exe"

client = Groq(
    api_key=os.environ.get("GROQ_API_KEY"),
    timeout=180.0 # Increased timeout for slow uploads
)

def get_audio_duration(file_path):
    """Uses ffprobe with absolute path."""
    try:
        abs_path = os.path.abspath(file_path)
        exe = FFPROBE_PATH if os.path.exists(FFPROBE_PATH) else 'ffprobe'
        cmd = [exe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', abs_path]
        output = subprocess.check_output(cmd).decode('utf-8').strip()
        return float(output)
    except Exception as e:
        print(f"Duration Error: {e}")
        return None

def transcribe_audio_stream(file_path):
    gc.collect()
    abs_input_path = os.path.abspath(file_path)
    total_duration = get_audio_duration(abs_input_path)
    file_size_mb = os.path.getsize(abs_input_path) / (1024 * 1024)
    full_transcript = []
    chunk_size = 600 # 10 minute chunks for stability
    
    # --- CASE 1: DIRECT UPLOAD (If under 24MB) ---
    if file_size_mb < 24:
        yield f">>> Uploading {file_size_mb:.1f}MB to AI Professor...", None
        try:
            with open(abs_input_path, "rb") as f:
                transcription = client.audio.transcriptions.create(
                    file=(os.path.basename(abs_input_path), f), 
                    model="whisper-large-v3-turbo", 
                    response_format="verbose_json"
                )
            
            count = 0
            for seg in getattr(transcription, 'segments', []):
                text = getattr(seg, 'text', '').strip()
                if text:
                    start = getattr(seg, 'start', 0)
                    line = f"[{int(start // 60):02}:{int(start % 60):02}] {text}"
                    yield line, None
                    full_transcript.append(line)
                    count += 1
            
            if count > 0:
                yield f"✅ Success: Captured {count} lines.", None
            else:
                yield "ℹ️ No speech detected in this file.", None

        except Exception as e:
            yield f"❌ Error: {str(e)}", None
        
        yield None, "\n".join(full_transcript)
        return

    # --- CASE 2: CHUNKING MODE (For files >= 24MB) ---
    num_chunks = max(1, int(-(total_duration // -chunk_size)))
    yield f">>> DETECTED {int(total_duration//60)} MINUTE LECTURE. PROCESSING {num_chunks} PARTS...", None

    ffmpeg_exe = FFMPEG_PATH if os.path.exists(FFMPEG_PATH) else 'ffmpeg'

    for i in range(num_chunks):
        progress = int(((i) / num_chunks) * 100)
        start_time = i * chunk_size
        chunk_filename = os.path.abspath(f"chunk_{i}_{int(time.time())}.mp3")
        yield f"[{progress}%] PROCESSING PART {i+1} of {num_chunks}...", None

        try:
            # Use High-bitrate MP3 for maximum Groq stability
            # Explicitly force output format to mp3 to avoid any ambiguity
            split_cmd = [
                ffmpeg_exe, '-y', '-ss', str(start_time), '-t', str(chunk_size),
                '-i', abs_input_path, '-ac', '1', '-ar', '16000', '-b:a', '192k',
                '-f', 'mp3', chunk_filename
            ]
            subprocess.run(split_cmd, check=True, capture_output=True)
            
            # Verify file exists and has data
            time.sleep(1.0) # Sync wait

            if not os.path.exists(chunk_filename) or os.path.getsize(chunk_filename) < 1000:
                yield f"⚠️ Skipping part {i+1}: Zero-byte file produced.", None
                continue

            # RETRY for Rate Limits (429)
            transcription = None
            for attempt in range(3):
                try:
                    with open(chunk_filename, "rb") as f:
                        transcription = client.audio.transcriptions.create(file=(os.path.basename(chunk_filename), f), model="whisper-large-v3-turbo", response_format="verbose_json")
                    break
                except Exception as api_e:
                    if "429" in str(api_e) and attempt < 2:
                        wait = 30 + (attempt * 30)
                        yield f"⏳ Rate limit! Waiting {wait}s...", None
                        time.sleep(wait)
                    else: raise api_e

            if transcription:
                count = 0
                for seg in getattr(transcription, 'segments', []):
                    text, seg_start = getattr(seg, 'text', '').strip(), getattr(seg, 'start', 0) + start_time
                    if text:
                        line = f"[{int(seg_start // 60):02}:{int(seg_start % 60):02}] {text}"
                        yield line, None
                        full_transcript.append(line)
                        count += 1
                if count > 0:
                    yield f"✅ Part {i+1}: Captured {count} lines.", None
                else:
                    yield f"ℹ️ Part {i+1}: No speech detected.", None

        except Exception as e:
            yield f"⚠️ Error in part {i+1}: {str(e)}", None
        finally:
            if os.path.exists(chunk_filename): os.remove(chunk_filename)

    yield None, "\n".join(full_transcript)
    gc.collect()
