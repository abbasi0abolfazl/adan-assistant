from ..contracts import SQLDraft
from ..errors import AppError
from ..llm import LLMProvider
from ..prompts import SQL
from ..tools.database import SCHEMA, RULES


class DatabaseAgent:
    def __init__(self, provider: LLMProvider, database):
        self.provider, self.database = provider, database

    def run(self, question: str, needs_calculator: bool, trace) -> dict:
        trace.add('database_agent', 'started')
        payload = {'question': question, 'schema': SCHEMA, 'semantic_rules': RULES,
                   'needs_calculator': needs_calculator}
        for attempt in range(2):
            draft = self.provider.structured(SQL, payload, SQLDraft, trace)
            if not draft.answerable:
                return {'sufficient': False, 'explanation': draft.explanation, 'result': None}
            if not draft.sql:
                raise AppError('SQL_INVALID', 'The model did not supply a query.', 502)
            trace.add('database_agent', 'sql_generated', attempt=attempt+1)
            try:
                trace.remaining()
                result = self.database.execute(draft.sql, draft.parameters)
                trace.remaining()
                trace.add('database_agent', 'read_only_sql_executed', row_count=result['row_count'],
                          truncated=result['truncated'])
                return {'sufficient': True, 'explanation': draft.explanation, 'result': result}
            except AppError as exc:
                trace.add('database_agent', 'sql_rejected', error_code=exc.code)
                if exc.code != 'SQL_INVALID' or attempt == 1:
                    raise
                # One bounded repair only. No raw database exception is sent out.
                payload['repair'] = {'previous_sql': draft.sql, 'parameters': draft.parameters,
                                     'error_code': exc.code,
                                     'instruction': 'Check schema, aliases, placeholders and SQLite syntax. One repair only.'}
        raise AppError('SQL_INVALID', 'Query generation failed.', 422)
