import numpy as np
import pytest
from app.documents import extract_chunks, normalize, flat
from app.retrieval import Retriever, normalize_vectors, build_retriever
from app.errors import AppError
from app.config import Settings
from app.trace import Trace
from .fakes import ScriptedProvider


def test_pdf_preprocessing_and_page_provenance(data_dir):
    chunks = extract_chunks(data_dir/'pdfs')
    assert len({c['filename'] for c in chunks}) == 3
    assert len({(c['filename'],c['page']) for c in chunks}) == 6
    assert len({c['source_id'] for c in chunks}) == len(chunks)
    assert all('NAVA INTERNAL HANDBOOK' not in c['text'] for c in chunks)
    assert all('Page 1 of 2' not in c['text'] for c in chunks)
    assert any('5%' in c['text'] for c in chunks)
    assert any('7 calendar days' in c['text'] for c in chunks)


def test_normalization():
    assert normalize('re-\nturn  policy\u200f') == 'return policy'
    assert flat('\u0643\u064a \n test') == '\u06a9\u06cc test'


def test_overlap(data_dir):
    chunks = extract_chunks(data_dir/'pdfs', chunk_words=60, overlap=10)
    first, second = chunks[0], chunks[1]
    assert first['page'] == second['page']
    assert first['text'].split()[-10:] == second['text'].split()[:10]


def test_real_cosine_algorithm_not_keyword_lookup():
    chunks = [{'source_id':'a','text':'alpha'},{'source_id':'b','text':'beta'}]
    provider = ScriptedProvider(embedding=[0.,1.])
    hits = Retriever(chunks, [[1,0],[0,2]], provider, top_k=1).search('any phrasing', Trace('test'))
    assert hits[0]['source_id'] == 'b' and hits[0]['score'] == 1.


def test_similarity_cutoff_returns_empty():
    r = Retriever([{'text':'x'}], [[1,0]], ScriptedProvider(embedding=[0,1]), min_score=0.5)
    assert r.search('unrelated', Trace('test')) == []


@pytest.mark.parametrize('vectors', [[[0,0]], [[float('nan'),1]], [1,2], [[float('inf'),1]]])
def test_invalid_vectors(vectors):
    with pytest.raises(AppError):
        normalize_vectors(vectors)


def test_dimension_mismatch():
    r = Retriever([{'text':'x'}], [[1,0]], ScriptedProvider(embedding=[1,0,0]))
    with pytest.raises(AppError):
        r.search('question', Trace('test'))


def test_cache_reused_and_changed_identity_rebuilt(data_dir,tmp_path):
    settings = Settings(data_dir=data_dir, runtime_dir=tmp_path)
    provider = ScriptedProvider(embedding=[1.]+[0.]*(settings.embedding_dimensions-1))
    first = build_retriever(settings, provider)
    original_calls = len(provider.calls)
    second = build_retriever(settings, provider)
    assert len(provider.calls) == original_calls
    assert np.array_equal(first.vectors,second.vectors)
    settings.embedding_model = 'test-changed-model'
    build_retriever(settings, provider)
    assert len(provider.calls) > original_calls


def test_corrupt_cache_rebuilt(data_dir,tmp_path):
    settings = Settings(data_dir=data_dir,runtime_dir=tmp_path)
    (tmp_path/'semantic-index.npz').write_bytes(b'broken')
    provider = ScriptedProvider(embedding=[1.]+[0.]*(settings.embedding_dimensions-1))
    assert build_retriever(settings,provider).chunks


def test_image_only_or_blank_page_is_explicit_error(tmp_path):
    from pypdf import PdfWriter
    writer=PdfWriter()
    writer.add_blank_page(width=100,height=100)
    writer.write(tmp_path/'blank.pdf')
    with pytest.raises(AppError) as error:
        extract_chunks(tmp_path)
    assert error.value.code=='PDF_TEXT_MISSING'


def test_changed_pdf_invalidates_cached_vectors(data_dir,tmp_path):
    import shutil
    copied=tmp_path/'data'
    shutil.copytree(data_dir,copied)
    settings=Settings(data_dir=copied,runtime_dir=tmp_path/'runtime')
    provider=ScriptedProvider(embedding=[1.]+[0.]*(settings.embedding_dimensions-1))
    build_retriever(settings,provider)
    count=len(provider.calls)
    pdf=next((copied/'pdfs').glob('*.pdf'))
    pdf.write_bytes(pdf.read_bytes()+b'\n% changed source fingerprint\n')
    build_retriever(settings,provider)
    assert len(provider.calls)>count
