"""Actual deterministic checks; not a live LLM or semantic-quality evaluation."""
import json
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.seed import seed_database
from app.documents import extract_chunks
from app.tools.database import ReadOnlySQL
from app.tools.calculator import evaluate
from app.errors import AppError

REFERENCE_SQL='''SELECT SUM(i.quantity*i.unit_price_irr-i.discount_irr) AS revenue_irr
FROM orders o JOIN order_items i ON i.order_id=o.order_id
WHERE o.status=? AND o.order_date>=? AND o.order_date<?'''


def main():
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'store.sqlite3'
        seed_database(ROOT/'data',path)
        database=ReadOnlySQL(path)
        jan=database.execute(REFERENCE_SQL,['completed','2026-01-01','2026-02-01'])
        feb=database.execute(REFERENCE_SQL,['completed','2026-02-01','2026-03-01'])
        a=jan['rows'][0]['revenue_irr']; b=feb['rows'][0]['revenue_irr']
        chunks=extract_chunks(ROOT/'data/pdfs')
        reserve_chunk=next(c for c in chunks if 'provisional return reserve rate is 5%' in c['text'])
        growth=evaluate('(current-previous)/previous*100',{'current':str(b),'previous':str(a)},2)
        reserve=evaluate('revenue*rate/100',{'revenue':str(b),'rate':'5'},0)
        attacks=[]
        for sql in ['DELETE FROM orders','DROP TABLE orders','PRAGMA writable_schema=ON',
                    "SELECT load_extension('/tmp/evil') FROM orders",'SELECT name FROM sqlite_master',
                    'SELECT nonexistent_column FROM orders']:
            try:
                database.execute(sql)
                attacks.append({'sql':sql,'blocked':False})
            except AppError as exc:
                attacks.append({'sql':sql,'blocked':True,'code':exc.code})
        result={'mode':'deterministic_reference_not_live_llm','generated_at':datetime.now(timezone.utc).isoformat(),
                'note':'SQL strings and rate in this CHECK SCRIPT are reference inputs, not model-generated answers.',
                'pdfs':len({x['filename'] for x in chunks}),'pages':len({(x['filename'],x['page']) for x in chunks}),
                'chunks':len(chunks),'january':jan,'february':feb,'growth':growth,'reserve':reserve,
                'reserve_source':reserve_chunk,'rejected_queries':attacks}
        assert a==100000000 and b==125000000 and growth['rounded_result']=='25.00'
        assert reserve['rounded_result']=='6250000' and all(x['blocked'] for x in attacks)
        out=ROOT/'reports/deterministic-checks.json'
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(result,indent=2))
        print(out)


if __name__=='__main__':
    main()
