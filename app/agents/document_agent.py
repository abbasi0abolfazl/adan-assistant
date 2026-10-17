import re
from decimal import Decimal, InvalidOperation
from ..contracts import DocumentAnswer
from ..documents import flat
from ..errors import AppError
from ..llm import LLMProvider
from ..prompts import DOCUMENTS
from ..tools.calculator import decimal_numbers


class DocumentAgent:
    def __init__(self, provider: LLMProvider, retriever):
        self.provider, self.retriever = provider, retriever

    def run(self, question: str, language: str, trace) -> dict:
        trace.add('document_agent', 'started')
        hits = self.retriever.search(question, trace)
        if not hits:
            return {'sufficient': False, 'answer': '', 'sources': [], 'numeric_variables': {}}
        answer = self.provider.structured(DOCUMENTS, {'question': question, 'language': language,
                     'evidence': [{'source_id': h['source_id'], 'text': h['text'],
                                  'filename': h['filename'], 'page': h['page']} for h in hits]},
                     DocumentAnswer, trace)
        if not answer.sufficient:
            trace.add('document_agent', 'insufficient_evidence')
            return {'sufficient': False, 'answer': answer.answer, 'sources': [], 'numeric_variables': {}}
        if not answer.answer.strip() or not answer.citations:
            raise AppError('DOCUMENT_UNGROUNDED', 'The document answer has no supporting citation.', 502)
        lookup = {hit['source_id']: hit for hit in hits}

        def check(source_id: str, quote: str):
            if source_id not in lookup or len(flat(quote)) < 4 or flat(quote) not in flat(lookup[source_id]['text']):
                raise AppError('DOCUMENT_UNGROUNDED', 'A document citation could not be verified.', 502)

        sources, seen = [], set()
        verified_quotes = []
        for citation in answer.citations:
            check(citation.source_id, citation.quote)
            verified_quotes.append(flat(citation.quote))
            key = (citation.source_id, flat(citation.quote))
            if key in seen:
                continue
            seen.add(key)
            hit = lookup[citation.source_id]
            sources.append({k: hit[k] for k in ('source_id','filename','title','page','score','document_sha256')}
                           | {'quote': citation.quote})
        # Reject numeric and temporal claims in generated prose unless the exact
        # value or a sufficient phrase is present in a verified citation. This
        # catches a retrieved related sentence from being used to support a
        # different claim about the same number.
        answer_numbers = {Decimal(value) for value in decimal_numbers(answer.answer)}
        cited_numbers = {Decimal(value) for quote in verified_quotes for value in decimal_numbers(quote)}
        if not answer_numbers <= cited_numbers:
            raise AppError('DOCUMENT_UNGROUNDED', 'A numeric answer claim is absent from the verified citations.', 502)
        answer_flat = flat(answer.answer)
        time_anchor_phrases = (
            'after delivery', 'from delivery', 'after dispatch', 'from dispatch',
            'from the invoice date', 'from invoice date',
        )
        translated_anchors = {
            'after delivery': ('پس از تحویل', 'بعد از تحویل'),
            'from delivery': ('از زمان تحویل', 'از تاریخ تحویل'),
            'after dispatch': ('پس از ارسال', 'بعد از ارسال'),
            'from dispatch': ('از زمان ارسال', 'از تاریخ ارسال'),
            'from the invoice date': ('از تاریخ فاکتور', 'از زمان صدور فاکتور'),
            'from invoice date': ('از تاریخ فاکتور', 'از زمان صدور فاکتور'),
        }
        for phrase in time_anchor_phrases:
            anchors = (phrase, *translated_anchors[phrase])
            if any(anchor in answer_flat for anchor in anchors) and not any(
                    any(anchor in quote for anchor in anchors) for quote in verified_quotes):
                raise AppError('DOCUMENT_UNGROUNDED', 'A time anchor in the answer is absent from the verified citations.', 502)
        numeric_variables = {}
        for fact in answer.numeric_facts:
            check(fact.source_id, fact.quote)
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', fact.name):
                raise AppError('DOCUMENT_UNGROUNDED', 'Invalid numeric fact identifier.', 502)
            key = 'doc_' + fact.name
            if key in numeric_variables:
                raise AppError('DOCUMENT_UNGROUNDED', 'Duplicate numeric fact identifier.', 502)
            try:
                number = Decimal(fact.value)
                values = [Decimal(x) for x in decimal_numbers(fact.quote)]
                if not number.is_finite() or abs(number) > Decimal('1e24') or number not in values:
                    raise ValueError('Numeric fact absent from quote')
            except (InvalidOperation, ValueError) as exc:
                raise AppError('DOCUMENT_UNGROUNDED', 'A numeric document fact could not be verified.', 502) from exc
            # Numeric facts must also be visible in the returned sources.
            if (fact.source_id, flat(fact.quote)) not in seen:
                hit = lookup[fact.source_id]
                sources.append({k: hit[k] for k in ('source_id','filename','title','page','score','document_sha256')}
                               | {'quote': fact.quote})
                seen.add((fact.source_id, flat(fact.quote)))
            numeric_variables[key] = {'value': str(number), 'source_id': fact.source_id, 'quote': fact.quote}
        trace.add('document_agent', 'grounded_answer', source_ids=sorted({x['source_id'] for x in sources}))
        return {'sufficient': True, 'answer': answer.answer, 'sources': sources,
                'numeric_variables': numeric_variables}
