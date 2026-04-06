import os
import sys

# Add the project root to sys.path so we can import utils
project_root = r"c:\Users\Prince Code\Desktop\StudyBot-main"
sys.path.append(project_root)

try:
    import docx
    from utils.text_extractor import extract_text_from_file
    print("✅ Imports successful.")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Create a test docx
test_path = os.path.join(project_root, "test_file.docx")
try:
    doc = docx.Document()
    doc.add_paragraph("This is a test document for StudBot AI extraction.")
    doc.save(test_path)
    print(f"✅ Test file created at {test_path}")
except Exception as e:
    print(f"❌ Failed to create test file: {e}")
    sys.exit(1)

# Test extraction using path
try:
    text = extract_text_from_file(test_path)
    print(f"✅ Extracted text (from path): '{text.strip()}'")
    if "StudBot AI" in text:
        print("🎉 EXTRACTION WORKED!")
    else:
        print("❌ Extraction returned empty or incorrect text.")
except Exception as e:
    print(f"❌ Extraction failed (path): {e}")

# Test extraction using file object
try:
    with open(test_path, 'rb') as f:
        # Mocking a filename attribute since Flask FileStorage has it
        class MockFile:
            def __init__(self, file_obj, name):
                self.file = file_obj
                self.filename = name
            def seek(self, pos): self.file.seek(pos)
            def read(self): return self.file.read()
            
        mock_file = MockFile(f, "test_file.docx")
        text = extract_text_from_file(mock_file)
        print(f"✅ Extracted text (from mock file object): '{text.strip()}'")
except Exception as e:
    print(f"❌ Extraction failed (file object): {e}")

# Cleanup
if os.path.exists(test_path):
    os.remove(test_path)
    print("🧹 Cleanup complete.")
