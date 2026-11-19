"""Causal display projection. Raw detector events are never edited or discarded.

Priority is editorial importance, NOT confidence, success probability or a trade
instruction. One projector belongs to one stream. Persist/rebuild it with the
same complete ordered tape; never recompute cooldown from a sliding tail.
"""
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone
import math

VERSION='presentation/0.2'
_BASIC={'doji','trend_bar','gap_open','body_gap','micro_gap','micro_channel','inside_bar','outside_bar'}
_KEY={'double_bottom','double_top','three_push_wedge','range_breakout','breakout_observation','failed_breakout','failed_failure','opening_reversal','measured_move','data_gap','session_reset'}
_STRUCTURAL_CANDIDATES = {
    'double_bottom', 'double_top', 'three_push_wedge', 'opening_reversal',
    'opening_breakout_mode', 'mtr_development', 'final_flag_development',
}


def _time(value):
    try:
        t=datetime.fromisoformat(value.replace('Z','+00:00'))
        if t.tzinfo is None or t.utcoffset() is None:raise ValueError()
        return t.astimezone(timezone.utc)
    except (ValueError,TypeError,AttributeError) as exc:
        raise ValueError('observed_at must be a timezone-aware ISO time') from exc


def priority(event):
    if event['family'] in _BASIC:return 0
    if event['family'] in _STRUCTURAL_CANDIDATES and event['status'] in ('candidate', 'confirmed', 'invalidated', 'reached', 'expired'):
        return 3
    if event['family'] in _KEY and event['status'] in ('confirmed','invalidated','reached','expired','observed'):return 3
    if event['status']=='candidate':return 2
    return 1


def _context_note(contexts):
    if any(x in ('warmup','range_or_transition','range_or_uncertain') for x in contexts):
        return '观察优先：预热、区间或过渡语境；缺乏明确方向不等于新的交易指令。'
    return '仅呈现结构变化；方向标签不是下单建议，未知胜率保持未知。'


class PresentationProjector:
    """Bounded incremental projection; snapshot returns detached records.

    Retains 200 groups, 4096 duplicate IDs and 512 editorial cooldown keys.
    Duplicate IDs in the retained replay window are ignored; older out-of-order
    data is rejected rather than silently replayed. Full input tape stays owned
    by the caller. update should receive all observations for each closed bar.
    """
    def __init__(self,min_priority=2,cooldown_minutes=15):
        if isinstance(min_priority,bool) or not isinstance(min_priority,int) or not 0<=min_priority<=3:
            raise ValueError('min_priority must be integer 0..3')
        if isinstance(cooldown_minutes,bool) or not isinstance(cooldown_minutes,(int,float)) or not math.isfinite(cooldown_minutes) or cooldown_minutes<0:
            raise ValueError('cooldown_minutes must be finite nonnegative')
        self.min_priority=min_priority;self.cooldown_minutes=cooldown_minutes
        self.groups=deque(maxlen=200);self.seen=set();self.seen_order=deque()
        self.last_shown={};self.last_time=None
        self.stats=Counter(raw_events=0,displayed_events=0,displayed_groups=0,
                           hidden_by_priority=0,hidden_by_cooldown=0,hidden_duplicate_ids=0)

    def update(self,events):
        events=list(events)
        # Validate the whole batch before changing state.
        last=self.last_time
        for e in events:
            if not isinstance(e,dict) or not all(isinstance(e.get(k),str) and e[k] for k in ('id','family','status','observed_at')):
                raise ValueError('event requires string id/family/status/observed_at')
            t=_time(e['observed_at'])
            if e['id'] in self.seen:continue
            if last is not None and t<last:raise ValueError('out-of-order presentation event')
            last=t
        changed=[]
        for e in events:
            if e['id'] in self.seen:
                self.stats['hidden_duplicate_ids']+=1
                continue
            self.seen.add(e['id']);self.seen_order.append(e['id'])
            if len(self.seen_order)>4096:self.seen.remove(self.seen_order.popleft())
            self.stats['raw_events']+=1
            t=_time(e['observed_at']);self.last_time=t
            if e['family'] in ('ema_gap','ema_first_return') or e.get('interpretation_role')=='LOCAL_DIAGNOSTIC':
                self.stats['hidden_local_diagnostic']+=1;continue
            p=priority(e)
            if p<self.min_priority:
                self.stats['hidden_by_priority']+=1;continue
            key=(e['family'],e['status'],e.get('direction','neutral'))
            previous=self.last_shown.get(key)
            if previous is not None and (t-previous).total_seconds()<self.cooldown_minutes*60:
                self.stats['hidden_by_cooldown']+=1;continue
            self.last_shown[key]=t
            if len(self.last_shown)>512:
                oldest=min(self.last_shown,key=self.last_shown.get);del self.last_shown[oldest]
            iso=t.isoformat()
            if self.groups and self.groups[-1]['observed_at']==iso:
                group=self.groups[-1]
            else:
                group={'observed_at':iso,'event_ids':[],'events':[],'priority':p,
                       'contexts':[],'context_note':'','presentation_version':VERSION}
                self.groups.append(group);self.stats['displayed_groups']+=1
            group['event_ids'].append(e['id']);group['events'].append(deepcopy(e))
            group['priority']=max(group['priority'],p)
            context=e.get('context')
            if context and context not in group['contexts']:group['contexts'].append(context)
            group['context_note']=_context_note(group['contexts'])
            self.stats['displayed_events']+=1
            if not changed or changed[-1] is not group:changed.append(group)
        return deepcopy(changed)

    def snapshot(self):
        stats=dict(self.stats)
        stats.update(retained_groups=len(self.groups),
                     hidden_events=stats['hidden_by_priority']+stats['hidden_by_cooldown']+stats.get('hidden_local_diagnostic',0),
                     note='展示过滤/聚合数量，不是信号准确率；原始事件由调用方完整保留。')
        return {'groups':deepcopy(list(self.groups)),'stats':stats,
                'config':{'min_priority':self.min_priority,'cooldown_minutes':self.cooldown_minutes},
                'presentation_version':VERSION}


def summarize_events(events,min_priority=2,cooldown_minutes=15):
    """Full-tape helper, preserving all selected groups (stream projector bounded)."""
    projector=PresentationProjector(min_priority,cooldown_minutes)
    all_groups=[]
    # Use timestamp batches so each returned group is complete at bar close.
    batch=[];stamp=None
    for e in events:
        current=e.get('observed_at') if isinstance(e,dict) else None
        if batch and current!=stamp:
            all_groups.extend(projector.update(batch));batch=[]
        batch.append(e);stamp=current
    if batch:all_groups.extend(projector.update(batch))
    result=projector.snapshot();result['groups']=all_groups
    result['stats']['retained_groups']=len(all_groups)
    return result
