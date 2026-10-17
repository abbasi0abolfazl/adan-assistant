import math
import re
from .contracts import Plan, FinalAnswer, CalculatorArguments, AskResponse
from .errors import AppError
from .llm import LLMProvider
from .prompts import ROUTER, FINAL, CALCULATOR
from .tools.calculator import decimal_numbers, evaluate


class Coordinator:
    def __init__(self, provider: LLMProvider, document_agent, database_agent):
        self.provider, self.documents, self.database = provider, document_agent, database_agent

    @staticmethod
    def _extract_user_variables(question: str, variables: dict, origins: dict) -> None:
        for index, number in enumerate(decimal_numbers(question)):
            key = f'user_n{index}'
            variables[key] = number
            origins[key] = {'source': 'user_question', 'value': number}

    @staticmethod
    def _extract_sql_variables(result: dict, variables: dict, origins: dict) -> int:
        count = 0
        for row_index, row in enumerate(result['rows']):
            for col_index, (column, value) in enumerate(row.items()):
                if type(value) in (int, float) and math.isfinite(value):
                    label = re.sub(r'[^a-zA-Z0-9_]', '_', column)[:32]
                    key = f'sql_r{row_index}_c{col_index}_{label}'
                    variables[key] = str(value)
                    origins[key] = {'source': 'sql_1', 'row': row_index, 'column': column, 'value': str(value)}
                    count += 1
        return count

    def _execute_calculator(
        self, plan: Plan, context: dict, variables: dict, origins: dict, trace
    ) -> tuple[dict, FinalAnswer]:
        turn = self.provider.choose_calculator(CALCULATOR, context, CalculatorArguments, trace)
        trace.add('calculator', 'tool_call_received', name=turn.name, call_id=turn.call_id)
        args = CalculatorArguments.model_validate(turn.arguments)
        computed = evaluate(args.expression, variables, args.precision)
        computed['origins'] = {k: origins[k] for k in computed['variables']}
        # Context-based calculations must actually depend on the SQL evidence.
        if plan.database_question and not any(k.startswith('sql_') for k in computed['variables']):
            raise AppError('CALC_UNGROUNDED', 'The calculation did not use the required SQL evidence.', 422)
        if plan.route == 'hybrid' and any(k.startswith('doc_') for k in variables) and not any(
                k.startswith('doc_') for k in computed['variables']):
            raise AppError('CALC_UNGROUNDED', 'The calculation did not use the extracted document value.', 422)
        trace.add('calculator', 'executed', expression=args.expression, result=computed['rounded_result'])
        final = self.provider.complete_tool(turn, {'calculation': computed, 'evidence': context},
                                             FINAL, FinalAnswer, trace)
        return {'tool': 'calculator', 'call_id': turn.call_id, **computed}, final

    @staticmethod
    def _validate_provenance(final: FinalAnswer, sources: list[dict], queries: list[dict], calculations: list[dict]) -> None:
        allowed_sources = {x['source_id'] for x in sources}
        if not final.answer.strip() or not set(final.used_source_ids) <= allowed_sources:
            raise AppError('FINAL_UNGROUNDED', 'Final answer contains invalid source references.', 502)
        if sources and not final.used_source_ids:
            raise AppError('FINAL_UNGROUNDED', 'Document evidence was omitted from the final answer.', 502)
        if set(final.used_sql_ids) != ({'sql_1'} if queries else set()):
            raise AppError('FINAL_UNGROUNDED', 'SQL provenance did not match the executed tools.', 502)
        if final.used_calculation != bool(calculations):
            raise AppError('FINAL_UNGROUNDED', 'Calculator provenance did not match the executed tools.', 502)

    def run(self, request, trace) -> AskResponse:
        trace.add('coordinator', 'planning')
        plan = self.provider.structured(ROUTER, request.model_dump(), Plan, trace)
        trace.add('coordinator', 'route_selected', route=plan.route, calculator=plan.needs_calculator)
        sources, queries, calculations, warnings = [], [], [], []

        def response(status, answer):
            trace.add('coordinator', 'finished', status=status)
            return AskResponse(request_id=trace.request_id, status=status, answer=answer,
                route=plan.route, sources=sources, sql=queries, calculations=calculations,
                trace=trace.events, warnings=warnings)

        def insufficient(message=''):
            default = ('There is insufficient evidence to answer this request reliably.' if request.language == 'en'
                       else '\u0628\u0631\u0627\u06cc \u067e\u0627\u0633\u062e \u0642\u0627\u0628\u0644 \u0627\u062a\u06a9\u0627 \u0628\u0647 \u0627\u06cc\u0646 \u067e\u0631\u0633\u0634\u060c \u0627\u0637\u0644\u0627\u0639\u0627\u062a \u06a9\u0627\u0641\u06cc \u062f\u0631 \u0645\u0646\u0627\u0628\u0639 \u0645\u0648\u062c\u0648\u062f \u0646\u06cc\u0633\u062a.')
            return response('insufficient_evidence', message or default)

        if plan.route == 'clarify':
            return response('clarification_required', plan.clarification)

        context = {'question': request.question, 'language': request.language,
                   'calculation_goal': plan.calculation_goal, 'documents': None, 'sql': None}
        variables, origins = {}, {}
        self._extract_user_variables(request.question, variables, origins)

        if plan.document_question:
            doc = self.documents.run(plan.document_question, request.language, trace)
            if not doc['sufficient']:
                return insufficient(doc['answer'])
            sources.extend(doc['sources'])
            context['documents'] = {'answer': doc['answer'], 'sources': sources}
            for key, fact in doc['numeric_variables'].items():
                variables[key] = fact['value']
                origins[key] = {'source': 'document', **fact}
            if plan.route == 'documents' and not plan.needs_calculator:
                return response('answered', doc['answer'])

        if plan.database_question:
            db = self.database.run(plan.database_question, plan.needs_calculator, trace)
            if not db['sufficient']:
                warnings.append(db['explanation'])
                return insufficient()
            result = db['result']
            queries.append(result)
            context['sql'] = result
            sql_variable_count = self._extract_sql_variables(result, variables, origins)
            if result['truncated']:
                warnings.append('SQL output was truncated; it is not a complete enumeration.')
                if plan.needs_calculator:
                    return insufficient()
            if plan.needs_calculator and sql_variable_count == 0:
                warnings.append('No numeric database value is available for the requested calculation; NULL is not zero.')
                return insufficient()

        context['available_variables'] = {k: {'value': v, 'origin': origins[k]} for k, v in variables.items()}

        if plan.needs_calculator:
            calc_record, final = self._execute_calculator(plan, context, variables, origins, trace)
            calculations.append(calc_record)
        else:
            final = self.provider.structured(FINAL, context, FinalAnswer, trace)

        self._validate_provenance(final, sources, queries, calculations)
        return response('answered', final.answer)
