import hashlib
import json
import os
from pathlib import Path
import numpy as np
from .documents import PREPROCESSING_VERSION, extract_chunks, flat
from .errors import AppError
from .llm import LLMProvider


def normalize_vectors(vectors, expected_rows=None):
    try:
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or (expected_rows is not None and len(matrix) != expected_rows):
            raise ValueError('Invalid matrix shape')
        if not np.isfinite(matrix).all():
            raise ValueError('Nonfinite vector')
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms <= 1e-12):
            raise ValueError('Zero vector')
        return matrix / norms
    except (TypeError, ValueError) as exc:
        raise AppError('EMBEDDING_INVALID', 'Embedding vectors failed validation.', 502) from exc


class Retriever:
    def __init__(self, chunks: list[dict], vectors, provider: LLMProvider, top_k=4, min_score=0.25):
        self.chunks, self.provider = chunks, provider
        self.vectors = normalize_vectors(vectors, len(chunks))
        self.top_k, self.min_score = top_k, min_score

    def search(self, question: str, trace) -> list[dict]:
        trace.remaining()
        query = normalize_vectors(self.provider.embed([flat(question)], trace), 1)[0]
        if query.shape[0] != self.vectors.shape[1]:
            raise AppError('INDEX_INCOMPATIBLE', 'Query and index embedding dimensions differ.', 503)
        scores = self.vectors @ query
        order = np.argsort(-scores, kind='stable')[:self.top_k]
        hits = [{**self.chunks[int(i)], 'score': round(float(scores[i]), 6)}
                for i in order if scores[i] >= self.min_score]
        trace.add('document_agent', 'semantic_retrieval', candidates=len(hits),
                  top_score=round(float(np.max(scores)), 6))
        return hits


def build_retriever(settings, provider: LLMProvider) -> Retriever:
    chunks = extract_chunks(settings.data_dir / 'pdfs', settings.chunk_words, settings.chunk_overlap)
    identity = {'preprocessing': PREPROCESSING_VERSION, 'chunks': chunks,
                'provider': settings.provider, 'embedding_model': settings.active_embedding_model,
                'dimensions': settings.embedding_dimensions,
                'provider_url': settings.openai_base_url if settings.provider == 'openai' else 'gemini-native',
                'chunk_words': settings.chunk_words, 'overlap': settings.chunk_overlap}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache = settings.runtime_dir / 'semantic-index.npz'
    vectors = None
    if cache.is_file():
        try:
            with np.load(cache, allow_pickle=False) as data:
                if str(data['fingerprint']) == fingerprint:
                    candidate = normalize_vectors(data['vectors'], len(chunks))
                    if candidate.shape[1] == settings.embedding_dimensions:
                        vectors = candidate
        except (ValueError, KeyError, OSError, AppError):
            # A corrupt cache is rebuildable; the source PDFs remain authoritative.
            vectors = None
    if vectors is None:
        raw = []
        for offset in range(0, len(chunks), 32):
            batch = chunks[offset:offset+32]
            raw.extend(provider.embed([f'Document: {x["title"]}\n{x["text"]}' for x in batch]))
        vectors = normalize_vectors(raw, len(chunks))
        if vectors.shape[1] != settings.embedding_dimensions:
            raise AppError('EMBEDDING_INVALID', 'Unexpected embedding dimensions during indexing.', 502)
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(f'.{os.getpid()}.tmp')
        try:
            with temporary.open('wb') as handle:
                np.savez_compressed(handle, fingerprint=np.array(fingerprint), vectors=vectors)
            os.replace(temporary, cache)
        finally:
            temporary.unlink(missing_ok=True)
    return Retriever(chunks, vectors, provider, settings.retrieval_top_k, settings.retrieval_min_score)
