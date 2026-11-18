#!/usr/bin/env python3
"""Offline, provenance-aware PA research retrieval. Does not import trading code."""
import argparse
from datetime import date
from urllib.parse import urlparse
import json
from pathlib import Path
import re
import sys
import unicodedata

BASE = Path(__file__).resolve().parent
METHODS = {'full_text_and_page_images', 'official_transcript_read',
           'indexed_substantive_text', 'full_page_text', 'selected_page_sections',
           'selected_paper_sections', 'index_only', 'full_captions_sampled_frames'}

def load(path=None):
    return json.loads(Path(path or BASE / 'concepts.json').read_text(encoding='utf-8'))

def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())

def validate(data):
    errors = []
    if not isinstance(data, dict): return ['root must be an object']
    if data.get('schema_version') != 1: errors.append('unsupported schema_version')
    def records(key):
        value = data.get(key)
        if not isinstance(value, list) or not value:
            errors.append(f'{key}: nonempty list required')
            return []
        if any(not isinstance(x, dict) for x in value):
            errors.append(f'{key}: every record must be an object')
        return [x for x in value if isinstance(x, dict)]
    sources, concepts = records('sources'), records('concepts')
    def ids(items, kind):
        found = set()
        for item in items:
            id_ = item.get('id')
            if not isinstance(id_, str) or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', id_):
                errors.append(f'{kind}: invalid id')
                continue
            if id_ in found: errors.append(f'{kind}: duplicate {id_}')
            found.add(id_)
        return found
    source_ids, concept_ids = ids(sources,'source'), ids(concepts,'concept')
    def strings(item, fields, prefix):
        for field in fields:
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f'{prefix}: nonempty string {field} required')
    for s in sources:
        prefix = f'source {s.get("id")}'
        strings(s, ['title','url','reviewed_at','review_method','review_scope','limitations','license_status'], prefix)
        if not isinstance(s.get('review_method'),str) or s['review_method'] not in METHODS: errors.append(f'{prefix}: unknown review_method')
        try:
            url=urlparse(s.get('url',''))
            if url.scheme!='https' or not url.hostname or '.' not in url.hostname or url.username or any(x.isspace() for x in s['url']): raise ValueError()
        except (ValueError,TypeError,AttributeError): errors.append(f'{prefix}: valid HTTPS URL required')
        try:
            value=s.get('reviewed_at')
            if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value): raise ValueError()
            date.fromisoformat(value)
        except (ValueError,TypeError): errors.append(f'{prefix}: ISO calendar date required')
    for c in concepts:
        prefix = f'concept {c.get("id")}'
        strings(c, ['title','category','summary','context','counterexample','evidence_status','implementation_status'], prefix)
        for key in ['aliases','causal_constraints','open_questions','related']:
            val = c.get(key)
            if not isinstance(val,list) or not val or any(not isinstance(x,str) or not x.strip() for x in val):
                errors.append(f'{prefix}: nonempty string list {key} required')
        related = c.get('related')
        if isinstance(related,list):
            for r in related:
                if not isinstance(r,str) or r not in concept_ids: errors.append(f'{prefix}: unknown related ID {r}')
        if c.get('implementation_status') not in ('not_implemented','partial_engineering_approximation','experimental_candidate_only','experimental_observation_only','methodology_only'):
            errors.append(f'{prefix}: unsupported implementation status')
        mapping = c.get('code_mapping')
        if not isinstance(mapping,dict) or mapping.get('status') != c.get('implementation_status'):
            errors.append(f'{prefix}: missing or inconsistent code mapping')
        else:
            strings(mapping,['audited_at','limits','coverage_reference'],prefix)
            files=mapping.get('files')
            if not isinstance(files,list): errors.append(f'{prefix}: mapping files must be list')
            else:
                for file in files:
                    if not isinstance(file,dict): errors.append(f'{prefix}: invalid mapped file')
                    else: strings(file,['path','symbols','sha256'],prefix)
        layers=c.get('claim_layers')
        expected={'research_conclusion':'source_grounded_paraphrase','engineering_interpretation':'project_synthesis_not_author_rule','open_questions':'unverified_research_questions'}
        if not isinstance(layers,dict) or any(layers.get(k)!=v for k,v in expected.items()):
            errors.append(f'{prefix}: explicit claim layers required')
        if c.get('research_conclusion') != c.get('summary'):
            errors.append(f'{prefix}: research_conclusion must match canonical summary')
        eng=c.get('engineering_interpretation')
        if not isinstance(eng,dict) or eng.get('status') != 'design_guidance_not_source_prescribed_rule':
            errors.append(f'{prefix}: engineering/source separation required')
        if isinstance(eng,dict) and eng.get('constraints') != c.get('causal_constraints'):
            errors.append(f'{prefix}: engineering constraints must match canonical causal_constraints')
        if c.get('evidence_status') != 'source_reviewed_unvalidated_on_soxl':
            errors.append(f'{prefix}: unsupported evidence status')
        refs = c.get('sources')
        if not isinstance(refs,list) or not refs:
            errors.append(f'{prefix}: source references required')
            continue
        substantive_support = False
        for ref in refs:
            if not isinstance(ref,dict):
                errors.append(f'{prefix}: malformed source reference'); continue
            sid = ref.get('source_id')
            if not isinstance(sid,str) or sid not in source_ids: errors.append(f'{prefix}: unknown source {sid}')
            strings(ref,['locator'],prefix)
            role=ref.get('support_role')
            if role not in ('concept_support','coverage_only','counterexample_support'): errors.append(f'{prefix}: source support_role required')
            src=next((s for s in sources if s.get('id')==sid),None)
            if src and src.get('review_method')=='index_only' and role!='coverage_only': errors.append(f'{prefix}: index-only source cannot substantiate concept')
            if src and isinstance(src.get('review_method'),str) and src['review_method'] in METHODS - {'index_only'} and role=='concept_support':
                substantive_support = True
        if not substantive_support:
            errors.append(f'{prefix}: at least one non-index concept_support source required')
    return errors

def search(data, query, category=None):
    """Exact bilingual alias/ID match first; lexical matches next. No probability."""
    q = normalize(query)
    if not q: return []
    ranked = []
    for c in data['concepts']:
        if category and c['category'] != category: continue
        names = [normalize(x) for x in [c['id'],c['title'],*c['aliases']]]
        body = normalize(' '.join([c['summary'],c['context'],c['counterexample'],*c['open_questions'],*c['causal_constraints']]))
        if q in names: score = 100
        elif any(q in n for n in names): score = 50
        elif q in [normalize(x) for x in c.get('related_search_terms',[])]: score = 30
        elif q in body: score = 20
        elif all(term in ' '.join(names)+' '+body for term in q.split()): score = 10
        else: continue
        ranked.append((score,c))
    return [c for _,c in sorted(ranked,key=lambda pair:(-pair[0],pair[1]['id']))]

def render(data):
    lines = ['# PA knowledge index', '', '> Generated from concepts.json. Research subset only; not implementation or validated trading edge.', '',
             '| ID | Concept | Category | Aliases |', '|---|---|---|---|']
    for c in sorted(data['concepts'], key=lambda x:(x['category'],x['id'])):
        lines.append(f'| [{c["id"]}](#{c["id"]}) | {c["title"]} | {c["category"]} | {", ".join(c["aliases"])} |')
    smap = {s['id']:s for s in data['sources']}
    for c in sorted(data['concepts'],key=lambda x:x['id']):
        lines += ['',f'<a id="{c["id"]}"></a>',f'## {c["title"]}', '', c['summary'], '',f'- Context: {c["context"]}',f'- Counterexample: {c["counterexample"]}', f'- Code status (audited snapshot): `{c["implementation_status"]}`. {c["code_mapping"]["limits"]}', '- Claim layers: summary = source-grounded paraphrase; engineering guidance = project synthesis; unresolved items = unverified questions.']
        for file in c['code_mapping']['files']:
            lines.append(f'- Code: [{file["path"]}](../{file["path"]}), `{file["symbols"]}`; snapshot hash recorded in JSON.')
        lines += ['- Causal constraint: '+x for x in c['causal_constraints']]
        lines += ['- Unresolved: '+x for x in c['open_questions']]
        for ref in c['sources']:
            s=smap[ref['source_id']]
            lines.append(f'- Source: [{s["title"]}]({s["url"]}), {ref["locator"]}; role: `{ref["support_role"]}`; review: `{s["review_method"]}`. Reviewed at: {s["reviewed_at"]}. Review scope: {s["review_scope"]}. Limit: {s["limitations"]}. License: `{s["license_status"]}`')
        lines.append('- Related: '+', '.join(f'[{r}](#{r})' for r in c['related']))
    return '\n'.join(lines)+'\n'

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,help='alternate JSON file to validate/query')
    subs=parser.add_subparsers(dest='command',required=True)
    p=subs.add_parser('search'); p.add_argument('query'); p.add_argument('--category')
    p=subs.add_parser('show'); p.add_argument('id')
    subs.add_parser('validate')
    p=subs.add_parser('render'); p.add_argument('--check',action='store_true')
    args=parser.parse_args(argv)
    try: data=load(args.data)
    except (OSError,ValueError) as e:
        print(str(e),file=sys.stderr); return 2
    errors=validate(data)
    if errors:
        print(json.dumps({'errors':errors},ensure_ascii=False,indent=2),file=sys.stderr);return 2
    if args.command=='validate':
        print(json.dumps({'valid':True,'concepts':len(data['concepts']),'sources':len(data['sources'])}));return 0
    if args.command=='render':
        text=render(data)
        if args.check:
            current=BASE/'INDEX.md'
            if not current.exists() or current.read_text(encoding='utf-8')!=text:
                print('INDEX.md is stale',file=sys.stderr);return 1
        else: print(text,end='')
        return 0
    if args.command=='search':
        result=search(data,args.query,args.category)
    else:
        result=next((c for c in data['concepts'] if c['id']==args.id),None)
        if result is None:
            print('Unknown concept ID',file=sys.stderr);return 1
        result=dict(result)
        ids={r['source_id'] for r in result['sources']}
        result['source_details']=[s for s in data['sources'] if s['id'] in ids]
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0

if __name__=='__main__': sys.exit(main())
