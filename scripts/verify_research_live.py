"""Verify real provider responses through the running API; never synthesize results."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    cases = [
        ('discovery', '/api/ai/discover', {'disease_id': 'MONDO:0012960', 'goal_id': 'natural_history'}),
        ('patient-answer', '/api/ai/ask', {'assessment_id': 'framework-for-syngap1', 'withdrawn_source_ids': [], 'question': 'What should we ask a researcher next?', 'mode': 'patient'}),
        ('withdrawn-answer', '/api/ai/ask', {'assessment_id': 'framework-for-syngap1', 'withdrawn_source_ids': ['PMID:42446932'], 'question': 'What changes if a paper is hidden?', 'mode': 'patient'}),
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {'checked_at': datetime.now(timezone.utc).isoformat(), 'scope': 'Real API/provider structure and current-state checks, not biomedical or clinical validation.', 'cases': []}
    for name, path, payload in cases:
        request = Request(args.base_url.rstrip('/') + path, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=120) as response:
                body = json.load(response)
        except HTTPError as exc:
            body = json.load(exc)
            safe = body.get('error', {})
            summary['cases'].append({'case': name, 'passed': False, 'status': exc.code, 'code': safe.get('code'), 'message': safe.get('message'), 'checks': safe.get('details', [])})
            print(name, 'FAILED', exc.code, safe.get('code'), safe.get('details', []), flush=True)
            continue
        field = 'discovery' if name == 'discovery' else 'answer'
        result = body[field]
        assert result['generation_mode'] in {'live', 'cached'}
        assert result['response_id'].startswith(('msg_', 'resp_'))
        if field == 'discovery':
            assert all(h['review_status'] == 'pending' and h['claim_origin'] == 'inferred' for h in result['hypotheses'])
        elif name == 'withdrawn-answer':
            assert 'DOI:10.1002/epi.70374' in body['withdrawn_source_ids']
            assert 'DOI:10.1002/epi.70374' not in result['cited_source_ids']
            assert 'PMID:42446932' not in result['cited_source_ids']
        (args.output_dir / f'{name}.json').write_text(json.dumps(body, indent=2, ensure_ascii=False) + '\n')
        row = {'case': name, 'passed': True, 'generation_mode': result['generation_mode'], 'model': result['model'], 'provider': result['provider'], 'response_id': result['response_id']}
        if field == 'discovery':
            row['hypotheses'] = len(result['hypotheses'])
            row['basis_kinds'] = [h['basis_kind'] for h in result['hypotheses']]
        else:
            row['cited_source_ids'] = result['cited_source_ids']
            row['evidence_state'] = result['evidence_state']
        summary['cases'].append(row)
        print(name, 'PASS', result['generation_mode'], result['response_id'], flush=True)
    (args.output_dir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    if not all(case['passed'] for case in summary['cases']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
