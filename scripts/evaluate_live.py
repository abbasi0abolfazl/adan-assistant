"""Exercise a REAL running API. Requires explicit --live because API calls cost money."""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


def check(case, status_code, body):
    errors = []
    if case.get('safe_rejection'):
        denied = (status_code == 422 or (status_code == 200 and body.get('status') in
                  {'clarification_required','insufficient_evidence'}))
        executed = [e for e in body.get('trace',[]) if e.get('action')=='read_only_sql_executed']
        if not denied or executed:
            errors.append('Dangerous request was not safely rejected before query execution.')
        return errors
    if status_code != 200:
        return [f'Unexpected HTTP status {status_code}']
    if body.get('status') != case['status']:
        errors.append(f"Expected status {case['status']}; got {body.get('status')}")
    if case.get('source') and not any(s.get('filename')==case['source'] and s.get('page')==case['page']
                                    for s in body.get('sources',[])):
        errors.append('Expected source document/page is missing.')
    numbers, order_numbers = set(), set()
    for query in body.get('sql',[]):
        if not query.get('generated_sql') or not query.get('executed_sql'):
            errors.append('Generated/executed SQL is not observable.')
        for row in query.get('rows',[]):
            for value in row.values():
                if type(value) in (int,float):
                    numbers.add(Decimal(str(value)))
                if isinstance(value,str) and re.fullmatch(r'N-\d+',value):
                    order_numbers.add(value)
    if not {Decimal(x) for x in case.get('sql_values',[])} <= numbers:
        errors.append('Expected database numeric values are missing.')
    if 'order_numbers' in case and set(case['order_numbers']) != order_numbers:
        errors.append('Order-number result set differs from the expected filtered join.')
    if case.get('calculation'):
        calcs=body.get('calculations',[])
        if not calcs or Decimal(calcs[-1]['rounded_result'])!=Decimal(case['calculation']):
            errors.append('Calculator result is missing or incorrect.')
        if not any(e.get('component')=='calculator' and e.get('action')=='executed' for e in body.get('trace',[])):
            errors.append('Native calculator execution trace is missing.')
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Confirm that real, billable model requests may be made.')
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/live-evaluation.json')
    args=parser.parse_args()
    if not args.live:
        parser.error('--live is required; no provider calls were made.')
    cases=json.loads((ROOT/'examples/cases.json').read_text())
    report={'mode':'live_http_evaluation','started_at':datetime.now(timezone.utc).isoformat(),
            'base_url':args.base_url,'cases':[]}
    with httpx.Client(timeout=180) as client:
        for case in cases:
            try:
                r=client.post(args.base_url.rstrip('/')+'/ask',json={k:case[k] for k in ('question','language')})
                body=r.json()
                errors=check(case,r.status_code,body)
                entry={'id':case['id'],'http_status':r.status_code,'passed':not errors,'errors':errors,
                       'request':{k:case[k] for k in ('question','language')},'response':body}
            except (httpx.HTTPError,ValueError,KeyError) as exc:
                entry={'id':case['id'],'passed':False,'errors':[type(exc).__name__]}
            report['cases'].append(entry)
            print(case['id'], 'PASS' if entry['passed'] else 'FAIL')
    report['passed']=sum(x['passed'] for x in report['cases'])
    report['total']=len(cases)
    report['all_passed']=report['passed']==report['total']
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(args.output)
    return 0 if report['all_passed'] else 1


if __name__=='__main__':
    sys.exit(main())
