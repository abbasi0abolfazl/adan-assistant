"""EXPLICIT TEST DOUBLES. Never imported by the runtime application."""
import json
from app.llm import ToolTurn


class ScriptedProvider:
    def __init__(self, replies=(), embedding=None):
        self.replies = list(replies)
        self.calls = []
        self.embedding = embedding or [1., 0.]
        self.tool_outputs = []

    def structured(self, instructions, payload, model, trace):
        self.calls.append({'kind': 'structured', 'model': model.__name__, 'payload': payload})
        if not self.replies:
            raise AssertionError('Unexpected model call')
        return model.model_validate(self.replies.pop(0))

    def embed(self, texts, trace=None):
        self.calls.append({'kind': 'embedding', 'texts': texts})
        return [self.embedding for _ in texts]

    def choose_calculator(self, instructions, payload, argument_model, trace):
        self.calls.append({'kind': 'native_function_call', 'payload': payload})
        arguments = argument_model.model_validate(self.replies.pop(0)).model_dump()
        return ToolTurn('test-call-1', 'calculator', arguments,
                        [{'role': 'user', 'content': json.dumps(payload)}], instructions)

    def complete_tool(self, turn, result, instructions, model, trace):
        self.tool_outputs.append({'call_id': turn.call_id, 'result': result})
        return self.structured(instructions, result, model, trace)

    def close(self):
        pass


class StaticRetriever:
    def __init__(self, hits):
        self.hits = hits

    def search(self, question, trace):
        trace.add('document_agent', 'semantic_retrieval_test_double', candidates=len(self.hits))
        return self.hits


def hit(text='The provisional return reserve rate is 5% of completed-order sales revenue.'):
    return {'source_id': 'sales:p2:c1:abcd1234', 'filename': 'sales_handbook.pdf',
            'title': 'Sales reporting', 'page': 2, 'score': 0.8,
            'document_sha256': 'abcd1234', 'text': text}


def plan(route='database', calculator=False):
    return {'route': route,
            'document_question': 'What is the reserve rate?' if route in {'documents','hybrid'} else None,
            'database_question': 'What was February 2026 revenue?' if route in {'database','hybrid'} else None,
            'needs_calculator': calculator,
            'calculation_goal': 'Calculate the requested percentage.' if calculator else None,
            'clarification': 'Which month and calendar?' if route == 'clarify' else None}


def final(answer='Result', doc=False, sql=True, calc=False):
    return {'answer': answer, 'used_source_ids': ['sales:p2:c1:abcd1234'] if doc else [],
            'used_sql_ids': ['sql_1'] if sql else [], 'used_calculation': calc}


REVENUE_SQL = '''SELECT SUM(i.quantity*i.unit_price_irr-i.discount_irr) AS revenue_irr
FROM orders o JOIN order_items i ON i.order_id=o.order_id
WHERE o.status=? AND o.order_date>=? AND o.order_date<?'''


def sql_draft(sql=REVENUE_SQL, parameters=None):
    return {'answerable': True, 'sql': sql,
            'parameters': parameters if parameters is not None else ['completed','2026-02-01','2026-03-01'],
            'explanation': 'Completed-order item revenue in the requested Gregorian period.'}


def doc_answer():
    source = hit()
    return {'sufficient': True, 'answer': 'The provisional reserve is 5% of revenue.',
            'citations': [{'source_id': source['source_id'], 'quote': source['text']}],
            'numeric_facts': [{'name': 'reserve_percent', 'value': '5',
                               'source_id': source['source_id'], 'quote': source['text']}]}
