import os 
import base64
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


def analyze_note_image(image_path):
    with open(image_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode("utf-8")

    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this lecture note. Extract the text and explain the concepts clearly for a student."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                    },
                ],
            }
        ],
        model="llama-3.2-vision-preview",
    )

    return chat_completion.choices[0].message.content
