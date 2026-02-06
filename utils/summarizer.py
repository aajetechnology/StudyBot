import os
import logging
from groq import Groq
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

class StudyAI:
    def __init__(self):
        self.api_key = os.getenv('GROQ_API_KEY')
        if not self.api_key:
            logger.error("GROQ_API_KEY not found in environment variables!")
            raise ValueError("Missing API Configuration")
        
        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.3-70b-versatile"

    def get_study_notes(self, transcript):
        """
        Generates structured study notes using a GENERATOR to prevent timeouts.
        """
        if not transcript or len(transcript.strip()) < 50:
            yield "The provided content was too brief to generate meaningful study notes.", None
            return

        truncated_transcript = transcript[:15000] 

        try:
            logger.info("Starting Streaming AI generation...")
            
            # Switch stream=True
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": (
                            "You are a professional academic tutor. Create highly structured study notes. "
                            "Use Markdown formatting, bold key terms, and include a summary section."
                        )
                    },
                    {"role": "user", "content": f"Please summarize this lecture transcript:\n\n{truncated_transcript}"}
                ],
                temperature=0.5,
                max_tokens=2048,
                stream=True  # CRITICAL: Now streaming
            )

            full_response = []
            for chunk in completion:
                content = chunk.choices[0].delta.content
                if content:
                    full_response.append(content)
                    # Yielding None as the final flag so process_log knows this is a log/pulse
                    yield content, None

            # Final yield with the full concatenated string for the DB/File saving
            yield None, "".join(full_response)

        except Exception as e:
            logger.error(f"Groq API Critical Error: {str(e)}")
            yield f"System busy: {str(e)}", None

ai_assistant = StudyAI()