import pytest
from app.agents.document_agent import DocumentAgent
from app.agents.database_agent import DatabaseAgent
from app.coordinator import Coordinator
from app.contracts import AskRequest
from app.errors import AppError
from app.trace import Trace
from .fakes import ScriptedProvider, StaticRetriever, hit, plan, doc_answer, sql_draft, final, REVENUE_SQL


def coordinator(provider, database, hits=None):
    return Coordinator(provider, DocumentAgent(provider,StaticRetriever(hits if hits is not None else [hit()])),
                       DatabaseAgent(provider,database))


def test_document_answer_cited(database):
    provider = ScriptedProvider([plan('documents'),doc_answer()])
    response = coordinator(provider,database).run(AskRequest(question='What is the reserve policy?',language='en'),Trace('test'))
    assert response.status == 'answered'
    assert response.sources[0]['page'] == 2
    assert response.sql == [] and response.calculations == []
    assert not provider.replies


def test_missing_documents_stops_hybrid(database):
    provider = ScriptedProvider([plan('hybrid',True)])
    response = coordinator(provider,database,[]).run(AskRequest(question='Missing policy plus sales'),Trace('test'))
    assert response.status == 'insufficient_evidence' and not response.sql
    assert len(provider.calls) == 1


def test_llm_insufficient_document_answer(database):
    provider = ScriptedProvider([plan('documents'), {'sufficient':False,'answer':'No international policy is specified.',
                                                'citations':[],'numeric_facts':[]}])
    response = coordinator(provider,database).run(AskRequest(question='How much to ship to Canada?'),Trace('test'))
    assert response.status == 'insufficient_evidence' and response.sources == []


@pytest.mark.parametrize('mutation', ['quote','source','numeric','conversion'])
def test_fabricated_document_evidence_rejected(mutation):
    answer = doc_answer()
    if mutation == 'quote': answer['citations'][0]['quote'] = 'The reserve rate is 99%.'
    if mutation == 'source': answer['citations'][0]['source_id'] = 'invented.pdf'
    if mutation == 'numeric': answer['numeric_facts'][0]['value'] = '99'
    if mutation == 'conversion': answer['numeric_facts'][0]['value'] = '0.05'
    provider = ScriptedProvider([answer])
    with pytest.raises(AppError) as exc:
        DocumentAgent(provider,StaticRetriever([hit()])).run('Reserve?','en',Trace('test'))
    assert exc.value.code == 'DOCUMENT_UNGROUNDED'


def test_numeric_time_claim_must_be_supported_by_same_verified_quote():
    related_but_insufficient = hit('The 7-day return window does not shorten the 12-month warranty.')
    answer = {'sufficient':True,
        'answer':'Customers may request a return within 7 days after delivery.',
        'citations':[{'source_id':related_but_insufficient['source_id'],
                      'quote':related_but_insufficient['text']}],
        'numeric_facts':[]}
    with pytest.raises(AppError) as error:
        DocumentAgent(ScriptedProvider([answer]),StaticRetriever([related_but_insufficient])).run(
            'How many days after delivery?','en',Trace('test'))
    assert error.value.code == 'DOCUMENT_UNGROUNDED'


def test_numeric_time_claim_passes_with_explicit_quote():
    explicit = hit('Customers may request a return within 7 calendar days after delivery.')
    answer = {'sufficient':True,
        'answer':'Customers may request a return within 7 calendar days after delivery.',
        'citations':[{'source_id':explicit['source_id'],'quote':explicit['text']}],
        'numeric_facts':[]}
    result = DocumentAgent(ScriptedProvider([answer]),StaticRetriever([explicit])).run(
        'How many days after delivery?','en',Trace('test'))
    assert result['sufficient']


def test_database_generated_sql_really_executes(database):
    provider = ScriptedProvider([plan(),sql_draft(),final('February revenue is 125,000,000 IRR.')])
    result = coordinator(provider,database).run(AskRequest(question='February 2026 revenue?',language='en'),Trace('test'))
    assert result.sql[0]['rows'] == [{'revenue_irr':125000000}]
    assert result.sql[0]['generated_sql'] == REVENUE_SQL


def test_hybrid_native_tool_and_real_calculation(database):
    provider = ScriptedProvider([plan('hybrid',True),doc_answer(),sql_draft(),
        {'expression':'sql_r0_c0_revenue_irr*doc_reserve_percent/100','precision':0},
        final('The provisional reserve is 6,250,000 IRR.',doc=True,sql=True,calc=True)])
    result = coordinator(provider,database).run(AskRequest(question='Reserve for February 2026?',language='en'),Trace('test'))
    assert result.calculations[0]['result'] == '6250000'
    assert result.calculations[0]['origins']['doc_reserve_percent']['source'] == 'document'
    assert provider.tool_outputs[0]['call_id'] == result.calculations[0]['call_id']
    assert result.route == 'hybrid'
    assert any(e['component']=='database_agent' and e['action']=='read_only_sql_executed' for e in result.trace)
    assert any(e['component']=='calculator' and e['action']=='executed' for e in result.trace)


def test_growth_real_sql_and_calculator(database):
    query = '''SELECT substr(o.order_date,1,7) AS month,
      SUM(i.quantity*i.unit_price_irr-i.discount_irr) AS revenue_irr
      FROM orders o JOIN order_items i ON i.order_id=o.order_id
      WHERE o.status=? AND o.order_date>=? AND o.order_date<? GROUP BY month ORDER BY month'''
    provider = ScriptedProvider([plan('database',True),
        sql_draft(query,['completed','2026-01-01','2026-03-01']),
        {'expression':'(sql_r1_c1_revenue_irr-sql_r0_c1_revenue_irr)/sql_r0_c1_revenue_irr*100','precision':2},
        final('Revenue grew 25.00%.',calc=True)])
    result = coordinator(provider,database).run(AskRequest(question='Revenue growth in February 2026?',language='en'),Trace('test'))
    assert result.calculations[0]['rounded_result'] == '25.00'
    assert result.sql[0]['rows'][0]['revenue_irr'] == 100000000


def test_user_arithmetic_uses_function_call(database):
    provider = ScriptedProvider([plan('calculator',True),{'expression':'user_n0*user_n1','precision':0},
                                 final('20',sql=False,calc=True)])
    result = coordinator(provider,database).run(AskRequest(question='Multiply 4 by 5.',language='en'),Trace('test'))
    assert result.calculations[0]['result'] == '20'


def test_clarification_no_tools(database):
    provider = ScriptedProvider([plan('clarify')])
    result = coordinator(provider,database).run(AskRequest(question='Sales this month?'),Trace('test'))
    assert result.status == 'clarification_required'
    assert not result.sql and not result.calculations


def test_sql_single_repair(database):
    provider = ScriptedProvider([sql_draft('SELECT missing FROM orders',[]),sql_draft()])
    response = DatabaseAgent(provider,database).run('Sales?',False,Trace('test'))
    assert response['result']['rows'] == [{'revenue_irr':125000000}]
    assert len(provider.calls) == 2
    assert 'repair' in provider.calls[-1]['payload']


def test_sql_repair_stops(database):
    provider = ScriptedProvider([sql_draft('SELECT missing FROM orders',[])]*2)
    with pytest.raises(AppError):
        DatabaseAgent(provider,database).run('Sales?',False,Trace('test'))
    assert len(provider.calls) == 2


def test_forbidden_query_not_repaired(database):
    provider = ScriptedProvider([sql_draft('DELETE FROM orders',[])])
    with pytest.raises(AppError) as error:
        DatabaseAgent(provider,database).run('Delete all orders',False,Trace('test'))
    assert error.value.code == 'SQL_FORBIDDEN'
    assert len(provider.calls) == 1


def test_missing_metric_refused(database):
    provider = ScriptedProvider([plan(),{'answerable':False,'sql':None,'parameters':[],
                                       'explanation':'Costs are absent; profit is unavailable.'}])
    result = coordinator(provider,database).run(AskRequest(question='Actual profit?'),Trace('test'))
    assert result.status == 'insufficient_evidence' and not result.sql


def test_null_value_does_not_become_zero(database):
    provider = ScriptedProvider([plan('database',True),
        sql_draft(parameters=['completed','2030-01-01','2030-02-01'])])
    result = coordinator(provider,database).run(AskRequest(question='Growth in 2030?'),Trace('test'))
    assert result.status == 'insufficient_evidence'
    assert result.sql[0]['rows'] == [{'revenue_irr':None}]
    assert result.calculations == []


def test_final_provenance_mismatch(database):
    provider = ScriptedProvider([plan(),sql_draft(),final(sql=False)])
    with pytest.raises(AppError) as error:
        coordinator(provider,database).run(AskRequest(question='February 2026 revenue?'),Trace('test'))
    assert error.value.code == 'FINAL_UNGROUNDED'


def test_calculation_cannot_ignore_sql(database):
    provider = ScriptedProvider([plan('database',True),sql_draft(),
                                {'expression':'1+1','precision':0}])
    with pytest.raises(AppError) as error:
        coordinator(provider,database).run(AskRequest(question='Growth February 2026?'),Trace('test'))
    assert error.value.code == 'CALC_UNGROUNDED'


def test_truncated_sql_blocks_calculation(db_path):
    from app.tools.database import ReadOnlySQL
    database=ReadOnlySQL(db_path,max_rows=1)
    provider=ScriptedProvider([plan('database',True),
        sql_draft('SELECT order_id AS sample_value FROM orders ORDER BY order_id',[])])
    result=coordinator(provider,database).run(AskRequest(question='Calculate from all orders'),Trace('test'))
    assert result.status=='insufficient_evidence'
    assert result.sql[0]['truncated'] and not result.calculations


def test_hybrid_calculation_requires_extracted_document_value(database):
    provider=ScriptedProvider([plan('hybrid',True),doc_answer(),sql_draft(),
                              {'expression':'sql_r0_c0_revenue_irr/100','precision':0}])
    with pytest.raises(AppError) as error:
        coordinator(provider,database).run(AskRequest(question='Reserve February 2026?'),Trace('test'))
    assert error.value.code=='CALC_UNGROUNDED'
