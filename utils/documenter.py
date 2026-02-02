import os
from docx import Document
from xhtml2pdf import pisa

def save_study_notes(summary, transcript, output_path):
    # This ensures the output folder exists relative to this file
    # Get the studAi root folder
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    final_destination = os.path.join(root_dir, 'output', os.path.basename(output_path))
    
    os.makedirs(os.path.dirname(final_destination), exist_ok=True)

    if final_destination.endswith('.docx'):
        doc = Document()
        doc.add_heading('Study Guide', 0)
        doc.add_paragraph(summary)
        doc.add_page_break()
        doc.add_heading('Transcript', 1)
        doc.add_paragraph(transcript)
        doc.save(final_destination)
    else:
        html = f"<h1>Summary</h1><p>{summary}</p><hr><h1>Transcript</h1><p>{transcript}</p>"
        with open(final_destination, "wb") as f:
            pisa.CreatePDF(html, dest=f)
    
    print(f"✅ FILE CREATED AT: {final_destination}")