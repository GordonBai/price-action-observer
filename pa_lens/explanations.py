"""Read-only source grounding for observations; never predicts trade success."""
import hashlib
import json
from pathlib import Path

_PATH=Path(__file__).resolve().parents[1]/'knowledge'/'concepts.json'
_RAW=_PATH.read_bytes()
KNOWLEDGE_VERSION=hashlib.sha256(_RAW).hexdigest()
_DATA=json.loads(_RAW)
_CARDS={x['id']:x for x in _DATA['concepts']}
_SOURCES={x['id']:x for x in _DATA['sources']}
FAMILY_CARDS={
    'double_bottom':['double-bottom','swing-structure'],
    'double_top':['double-top','swing-structure'],
    'range_breakout':['breakout-follow-through','measured-move'],
    'measured_move':['measured-move'],
    'inside_bar':['inside-sequences'], 'outside_bar':['inside-sequences'],
    'high_attempt':['second-entry'], 'low_attempt':['second-entry'],
    'three_push_wedge':['swing-structure'],
    'data_gap':['evidence-boundary'], 'session_reset':['session-and-liquidity-context'],
}

def ground_event(event):
    """Attach original KB paraphrases, never replace detector-specific evidence."""
    ids=event.get('knowledge_ids') or FAMILY_CARDS.get(event['family'],['evidence-boundary'])
    unknown=[x for x in ids if x not in _CARDS]
    if unknown:raise ValueError('unknown knowledge IDs: '+','.join(unknown))
    event['knowledge_ids']=list(dict.fromkeys(ids))
    event['knowledge_version']=KNOWLEDGE_VERSION
    event['interpretation_type']='observation_not_recommendation'
    event['knowledge_references']=[{
        'id':key,'title':_CARDS[key]['title'],
        'summary':_CARDS[key]['research_conclusion'],
        'counterexample':_CARDS[key]['counterexample'],
        'sources':[{'url':_SOURCES[r['source_id']]['url'],'locator':r['locator'],
                    'review_method':_SOURCES[r['source_id']]['review_method'],
                    'review_scope':_SOURCES[r['source_id']]['review_scope'],
                    'limitations':_SOURCES[r['source_id']]['limitations']} for r in _CARDS[key]['sources']],
        'source_urls':list(dict.fromkeys(_SOURCES[s['source_id']]['url'] for s in _CARDS[key]['sources'])),
    } for key in event['knowledge_ids']]
    event['uncertainty']=event.get('uncertainty') or '数值判定是项目工程近似；不能由价格形态证明机构动机、未来方向或交易胜率。'
    return event
