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

        # NEW: Process in chunks if transcript is long
        chunk_size = 15000
        overlap = 1000
        text_chunks = []
        for i in range(0, len(transcript), chunk_size - overlap):
            text_chunks.append(transcript[i:i + chunk_size])

        # Step 1: Create a combined map if there are multiple chunks
        if len(text_chunks) > 1:
            intermediate_summaries = []
            for idx, chunk in enumerate(text_chunks[:10]): # Process up to 10 chunks (~150k chars)
                prompt = f"Summarize this part of the lecture in detail for notes. Part {idx+1}:\n\n{chunk}"
                try:
                    res = self.client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "user", "content": prompt}])
                    intermediate_summaries.append(res.choices[0].message.content)
                except: continue
            final_context = "\n\n".join(intermediate_summaries)
        else:
            final_context = transcript

        # Step 2: Final Academic Synthesis
        system_prompt = """
        You are a world-class academic scribe. Convert the provided transcript into Professional Lecture Notes.
        Use the Cornell Note-Taking framework:
        1. HEADER: Topic, Date, and 3-5 'Key Learning Objectives'.
        2. STRUCTURED NOTES: Full main concepts with a clear hierarchy (use Headings and Subheadings).
        3. VOCABULARY: Definitions for technical jargon or key terms mentioned.
        4. SUMMARY: A 2-paragraph concluding synthesis.
        Use Markdown (bolding, bullet points) to make it exam-ready.
        """
        
        full_response = []
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Create Professional Study Notes from this context:\n\n{final_context}"}
                ],
                temperature=0.4,
                stream=True
            )
            for chunk in completion:
                content = chunk.choices[0].delta.content
                if content:
                    full_response.append(content)
                    yield content, None
            yield None, "".join(full_response)
        except Exception as e:
            yield None, f"Error: {str(e)}"

ai_assistant = StudyAI()
