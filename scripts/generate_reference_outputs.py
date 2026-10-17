"""Create clearly labelled fixture-driven traces with real SQLite/Calculator results.
This is NOT a replacement for evaluate_live.py and never claims live LLM execution.
"""
import json
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.documents import extract_chunks
from app.seed import seed_database
from app.tools.database import ReadOnlySQL
from app.agents.document_agent import DocumentAgent
from app.agents.database_agent import DatabaseAgent
from app.coordinator import Coordinator
from app.contracts import AskRequest
from app.trace import Trace
from tests.fakes import ScriptedProvider, StaticRetriever, plan, sql_draft, final


def main():
    chunks=extract_chunks(ROOT/'data/pdfs')
    source=next(c for c in chunks if 'provisional return reserve rate is 5%' in c['text'])
    source={**source,'score':0.8}
    quote='The provisional return reserve rate is 5% of completed-order sales revenue for the selected reporting period.'
    doc={'sufficient':True,'answer':'The provisional reserve is 5% of completed-order revenue.',
         'citations':[{'source_id':source['source_id'],'quote':quote}],
         'numeric_facts':[{'name':'reserve_percent','value':'5','source_id':source['source_id'],'quote':quote}]}
    final_doc=final('The provisional return reserve is 6,250,000 IRR; it is not an actual refund total.',doc=True,calc=True)
    final_doc['used_source_ids']=[source['source_id']]
    definitions=[
       ('rag',AskRequest(question='What does the sales handbook say about the provisional reserve?',language='en'),
        [plan('documents'),doc]),
       ('database',AskRequest(question='What was completed-order revenue for February 2026?',language='en'),
        [plan(),sql_draft(),final('February 2026 completed-order revenue is 125,000,000 IRR.')]),
       ('hybrid',AskRequest(question='Calculate the provisional reserve for February 2026 revenue.',language='en'),
        [plan('hybrid',True),doc,sql_draft(),
         {'expression':'sql_r0_c0_revenue_irr*doc_reserve_percent/100','precision':0},final_doc])]
    examples=[]
    with tempfile.TemporaryDirectory() as temporary:
        db_path=Path(temporary)/'store.sqlite3'; seed_database(ROOT/'data',db_path)
        database=ReadOnlySQL(db_path)
        for name,request,replies in definitions:
            provider=ScriptedProvider(replies)
            flow=Coordinator(provider,DocumentAgent(provider,StaticRetriever([source])),DatabaseAgent(provider,database))
            answer=flow.run(request,Trace('fixture-'+name)).model_dump()
            examples.append({'name':name,'request':request.model_dump(),'response':answer})
    (ROOT/'examples/reference_outputs.json').write_text(json.dumps({
        'mode':'scripted_model_contract_examples',
        'warning':'LLM replies and retrieval ranking are TEST FIXTURES. SQLite execution, PDF extraction, quote validation and calculator arithmetic actually ran. These are NOT live LLM outputs.',
        'live_capture_command':'python scripts/evaluate_live.py --live',
        'examples':examples},indent=2))
    print(ROOT/'examples/reference_outputs.json')


if __name__=='__main__':main()
