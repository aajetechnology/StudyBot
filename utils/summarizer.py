import os
import logging
from groq import Groq
from dotenv import load_dotenv

# Set up structured logging instead of print()
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

    def get_study_notes(self, transcript, format_type="markdown"):
        """
        Generates structured study notes with error handling and input validation.
        """
        if not transcript or len(transcript.strip()) < 50:
            logger.warning("Transcript received is too short for processing.")
            return "The provided content was too brief to generate meaningful study notes."

        # Production tip: Limit input size to stay within model context limits
        truncated_transcript = transcript[:15000] 

        try:
            logger.info(f"Starting AI generation for transcript ({len(truncated_transcript)} chars)")
            
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
                temperature=0.5, # Lower temperature = more factual/stable output
                max_tokens=2048,
                top_p=1,
                stream=False
            )

            result = completion.choices[0].message.content
            
            if not result:
                throw_err = "AI returned an empty response."
                logger.error(throw_err)
                return "Error: AI failed to generate content."

            logger.info("AI generation successful.")
            return result

        except Exception as e:
            logger.error(f"Groq API Critical Error: {str(e)}")
            
            return "System busy: AI processing failed. Please try again in a few moments."


ai_assistant = StudyAI()