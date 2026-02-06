import os
import base64
from pypdf import PdfReader
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def process_files(file_paths):
    full_lecture_content = ""
    
    for path in file_paths:
        if path.endswith('.pdf'):
            # Extract text from digital PDF
            reader = PdfReader(path)
            for page in reader.pages:
                full_lecture_content += page.extract_text() + "\n"
        
        elif path.lower().endswith(('.png', '.jpg', '.jpeg')):
            # Use Groq Vision for snapped notes (OCR)
            with open(path, "rb") as img:
                b64_image = base64.b64encode(img.read()).decode('utf-8')
            
            response = client.chat.completions.create(
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Transcribe all text from this note exactly."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                    ]
                }],
                model="llama-3.2-11b-vision-preview",
            )
            full_lecture_content += response.choices[0].message.content + "\n"
            
    return full_lecture_content

def lecture_student(content):
    # The "AI Professor" role
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a helpful Professor. Use the provided notes to teach the student."},
            {"role": "user", "content": f"Here are my lecture notes: {content}\n\nPlease explain the main concepts and offer to answer questions."}
        ],
        model="llama-3.3-70b-versatile",
    )
    return response.choices[0].message.content