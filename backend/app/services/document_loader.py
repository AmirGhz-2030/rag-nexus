import uuid
import re
from typing import List, Dict, Any
import pypdf

class DocumentProcessor:
    """Document loader and recursive semantic chunker."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract_text(self, file_content: bytes, file_name: str) -> str:
        """Extract plain text based on file extension."""
        if file_name.endswith('.pdf'):
            import io
            pdf_reader = pypdf.PdfReader(io.BytesIO(file_content))
            text = ""
            for page in pdf_reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            return text
        else:
            # Fallback for txt, md, code files
            return file_content.decode("utf-8", errors="ignore")

    def create_chunks(self, text: str, document_name: str) -> List[Dict[str, Any]]:
        """Split text into recursive overlapping chunks with metadata."""
        # Simple recursive splitting by double newline, newline, space
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = ""
        chunk_idx = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 1 <= self.chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "content": current_chunk,
                        "metadata": {
                            "source": document_name,
                            "chunk_index": chunk_idx,
                            "length": len(current_chunk)
                        }
                    })
                    chunk_idx += 1
                
                # Overlap logic
                overlap = current_chunk[-self.chunk_overlap:] if len(current_chunk) >= self.chunk_overlap else ""
                current_chunk = (overlap + "\n\n" + para) if overlap else para

        if current_chunk:
            chunks.append({
                "id": str(uuid.uuid4()),
                "content": current_chunk,
                "metadata": {
                    "source": document_name,
                    "chunk_index": chunk_idx,
                    "length": len(current_chunk)
                }
            })

        return chunks
