from pypdf import PdfReader

def parse_resume(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text.strip()
