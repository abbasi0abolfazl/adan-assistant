import hashlib
import re
import unicodedata
from collections import Counter
from pathlib import Path
from pypdf import PdfReader
from .errors import AppError

PREPROCESSING_VERSION = '3-normalize-page-margins-word-overlap'
BIDI = dict.fromkeys(map(ord, '\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069'), None)
CHARACTERS = str.maketrans({'\u064a':'\u06cc', '\u0643':'\u06a9', '\u00ad':'', '\u00a0':' '})


def normalize(text: str) -> str:
    text = unicodedata.normalize('NFKC', text).translate(BIDI).translate(CHARACTERS)
    text = re.sub(r'([A-Za-z])-\s*\n\s*([a-z])', r'\1\2', text)
    return '\n'.join(re.sub(r'[ \t]+', ' ', line).strip() for line in text.splitlines()).strip()


def flat(text: str) -> str:
    return ' '.join(normalize(text).split())


def extract_chunks(pdf_dir: Path, chunk_words: int = 180, overlap: int = 30) -> list[dict]:
    if overlap >= chunk_words:
        raise AppError('CONFIG_INVALID', 'Chunk overlap must be smaller than chunk size.', 503)
    chunks = []
    paths = sorted(Path(pdf_dir).glob('*.pdf'))
    if not paths:
        raise AppError('DOCUMENTS_MISSING', 'No PDF source documents were found.', 503)
    for path in paths:
        if path.stat().st_size > 10_000_000:
            raise AppError('PDF_TOO_LARGE', 'A sample PDF exceeds the 10 MB bound.', 503)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            reader = PdfReader(path)
            if reader.is_encrypted or len(reader.pages) > 30:
                raise ValueError('Encrypted or oversized document')
            pages = [normalize(page.extract_text() or '') for page in reader.pages]
            title = str((reader.metadata or {}).get('/Title') or path.stem)
        except Exception as exc:
            raise AppError('PDF_INVALID', 'A source PDF could not be processed.', 503) from exc
        if any(len(flat(page)) < 20 for page in pages):
            raise AppError('PDF_TEXT_MISSING', 'A page has no usable text; scanned PDFs require an explicit OCR pipeline.', 503)
        # Only repeated lines in page margins are candidates. Do not deduplicate
        # all document text: repeated clauses may be meaningful evidence.
        margins = Counter()
        for page in pages:
            lines = [line for line in page.splitlines() if line]
            margins.update({line for line in lines[:2]+lines[-2:] if len(line) <= 120})
        repeated = {line for line, count in margins.items() if count >= 2}
        for page_number, page in enumerate(pages, 1):
            lines = [line for line in page.splitlines() if line]
            cleaned = []
            for index, line in enumerate(lines):
                is_margin = index < 2 or index >= len(lines)-2
                if is_margin and (line in repeated or re.fullmatch(r'Page \d+ of \d+', line, re.I)):
                    continue
                cleaned.append(line)
            words = flat('\n'.join(cleaned)).split()
            start, chunk_no = 0, 1
            while start < len(words):
                text = ' '.join(words[start:start+chunk_words])
                source_id = f'{path.stem}:p{page_number}:c{chunk_no}:{digest[:8]}'
                chunks.append({'source_id': source_id, 'filename': path.name, 'title': title,
                               'page': page_number, 'chunk': chunk_no, 'text': text,
                               'document_sha256': digest})
                if start+chunk_words >= len(words):
                    break
                start += chunk_words-overlap
                chunk_no += 1
    if not chunks:
        raise AppError('DOCUMENTS_EMPTY', 'No usable document chunks were produced.', 503)
    return chunks
