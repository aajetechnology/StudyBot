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
        if not transcript or len(transcript.strip()) < 50:
            yield "Content too brief...", "The provided content was too brief."
            return

        truncated_transcript = transcript[:15000] 
        full_response = []

        try:
            logger.info("Starting Streaming AI generation...")
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional academic tutor..."},
                    {"role": "user", "content": f"Summarize this:\n\n{truncated_transcript}"}
                ],
                temperature=0.5,
                max_tokens=2048,
                stream=True
            )

            for chunk in completion:
                content = chunk.choices[0].delta.content
                if content:
                    full_response.append(content)
                    yield content, None

            # CRITICAL: If the AI returned nothing, don't leave it as None
            final_summary = "".join(full_response)
            if not final_summary:
                final_summary = "AI was unable to generate a summary for this transcript."
            
            yield None, final_summary

        except Exception as e:
            logger.error(f"Groq API Critical Error: {str(e)}")
            # Even on error, return a string so the DB save doesn't crash
            yield None, f"Summary Generation Error: {str(e)}"

ai_assistant = StudyAI()