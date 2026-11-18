"""Bounded, causal *heuristic* attempt and three-push observations.

Not official Brooks algorithms, trade recommendations, or full MTR detection.

Attempt contract (fixed engineering approximation):
- A lower high starts/rearms a high-attempt pullback; a later higher high,
  after at least one pullback bar, records H1 then H2. Mirror for L1/L2.
- Consecutive higher highs never increment H count. Outside bars are excluded
  because OHLC does not tell whether their high or low occurred first.
- Episode expires after setup_expiry bars (default20), or after a prior attempt
  and a close through the episode's original reference extreme. Caller resets
  on session/gap. Counts and context labels are separate, not setup quality.
- The event is observed after the attempt bar closes, not backdated to its
  preceding signal bar. No trade price or executable-entry event is emitted.

Three-push contract:
- Strict 2-left/2-right extrema, five alternating pivots. Same-side redundant
  pivots are replaced only by a more extreme value. An ambiguous simultaneous
  high/low pivot is ignored.
- The first two pushes progress >=0.25 current ATR. Third remains beyond first
  and no more than0.5 ATR behind second. Each intervening counter-swing is at
  least0.5 ATR. Third need NOT make a fresh extreme; convergence not required.
- Emits candidate after right-side confirmation. On later bars only, close
  through the last counter-swing confirms local structure (NOT a major trend
  reversal). New extreme beyond all three pushes invalidates; expiry is fixed.
  If both levels trade in one bar, invalidation takes priority (path unknown).

Defaults are engineering approximations and must be tested separately by
instrument/timeframe. This module uses no full-history lookback or order API.
"""
from collections import deque
from datetime import datetime
import hashlib
import json
import math


class AdvancedDetector:
    def __init__(self, config=None):
        self.expiry=getattr(config,'setup_expiry',20)
        self.max_span=getattr(config,'max_pattern_bars',60)
        self.bars=deque(maxlen=5)
        self.swings=deque(maxlen=5)
        self.episodes={'high':None,'low':None}
        self.index=-1
        self.last=None
        self.stream=None
        self.wedges=deque(maxlen=20)

    def _event(self,family,direction,bar,anchors,evidence,context,**extra):
        status=extra.pop('status','candidate' if family=='three_push_wedge' else 'observed')
        raw=[self.stream,family,status,direction,bar.time,anchors]
        return {'id':hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()[:20],
                'family':family,'status':status,
                'direction':direction,'observed_at':bar.time,'confirmed_at':bar.time if status in ('confirmed','invalidated') else None,
                'anchors':anchors,'evidence':evidence,'context':context,'probability':None,
                'rule_version':'advanced-heuristic/0.2',
                'knowledge_ids':['swing-structure'] if family=='three_push_wedge' else ['second-entry','pullback-flag'],
                'uncertainty':'工程阈值近似；未验证预测有效性；三推不等于抛物线加速或完整MTR；不等于完整Brooks定义',
                'explanation':(('三推楔形：'+status) if family=='three_push_wedge' else '回调尝试计数')+'：'+'；'.join(evidence)+'。不是已确认交易或实际成交。',**extra}

    def _attempts(self,bar,prev,context):
        out=[]
        outside=bar.high>prev.high and bar.low<prev.low
        for side in ('high','low'):
            episode=self.episodes[side]
            crossed=False
            if episode:
                crossed=bar.close>episode['reference'] if side=='high' else bar.close<episode['reference']
                if self.index-episode['start']>self.expiry:
                    self.episodes[side]=None;episode=None
            if outside:
                if episode and crossed:self.episodes[side]=None
                continue
            previous=getattr(prev,side);value=getattr(bar,side)
            pullback=value<previous if side=='high' else value>previous
            attempt=value>previous if side=='high' else value<previous
            if pullback:
                if episode is None:
                    episode={'start':self.index,'time':bar.time,'reference':previous,'count':0,'armed':True}
                    self.episodes[side]=episode
                else:episode['armed']=True
            elif attempt and episode and episode['armed']:
                episode['count']+=1;episode['armed']=False
                if episode['count']>2:continue
                direction='long' if side=='high' else 'short'
                label=('bull_pullback' if context=='trend_up' else 'countertrend_in_bear' if context=='trend_down' else 'range_or_uncertain') if side=='high' else ('bear_pullback' if context=='trend_down' else 'countertrend_in_bull' if context=='trend_up' else 'range_or_uncertain')
                name=('H' if side=='high' else 'L')+str(episode['count'])
                out.append(self._event(side+'_attempt',direction,bar,
                    {'episode_start':episode['time'],'episode_reference':episode['reference'],'signal_bar_time':prev.time,'signal_bar_extreme':previous},
                    [name+'工程近似：两次尝试之间必须有新的回调','计数不是入场质量；当前语境 '+label,'当前bar收盘后才可知，不回填到信号bar'],context,
                    attempt_count=episode['count'],attempt_label=name,context_label=label))
            # Observe an armed attempt before the same close ends the episode.
            if episode and episode['count'] and crossed:self.episodes[side]=None
        return out

    def _wedge(self,bar,context,atr):
        if len(self.bars)<5:return []
        center=self.bars[2];neighbors=[self.bars[i] for i in (0,1,3,4)]
        high=all(center.high>b.high for b in neighbors)
        low=all(center.low<b.low for b in neighbors)
        if high==low:return []
        side='high' if high else 'low'
        pivot={'kind':side,'price':getattr(center,side),'index':self.index-2,'time':center.time,'confirmed_at':bar.time}
        if self.swings and self.swings[-1]['kind']==side:
            old=self.swings[-1]
            extreme=pivot['price']>old['price'] if high else pivot['price']<old['price']
            if not extreme:return []
            self.swings[-1]=pivot
        else:self.swings.append(pivot)
        if len(self.swings)<5:return []
        a,counter1,b,counter2,c=self.swings
        if a['kind']!=side or b['kind']!=side or c['index']-a['index']>self.max_span:return []
        sign=1 if high else -1
        first,second,third=(sign*p['price'] for p in (a,b,c))
        if second-first<.25*atr or third<=first or third<second-.5*atr:return []
        if abs(a['price']-counter1['price'])<.5*atr or abs(b['price']-counter2['price'])<.5*atr:return []
        direction='short' if high else 'long'
        anchors={'pushes':[dict(p) for p in (a,b,c)],'counter_swings':[dict(counter1),dict(counter2)],'pivot_right_bars':2,'atr_at_observation':atr}
        event=self._event('three_push_wedge',direction,bar,anchors,
                ['三个方向性摆动之间有反向摆动；第三推允许未创新极值','已等右侧2根确认，尚未确认反转','不要求几何收敛；数值阈值为工程近似'],context)
        self.wedges.append({'event':event,'index':self.index,'level':counter2['price'],
                            'extreme':max(p['price'] for p in (a,b,c)) if high else min(p['price'] for p in (a,b,c))})
        return [event]

    def _wedge_lifecycle(self,bar,context):
        out=[]
        for pending in list(self.wedges):
            original=pending['event'];long=original['direction']=='long'
            invalid=bar.low<pending['extreme'] if long else bar.high>pending['extreme']
            confirmed=bar.close>pending['level'] if long else bar.close<pending['level']
            if invalid:
                status='invalidated';reason='原趋势方向超过三推极值，旧候选失效；同根路径未知时失效优先'
            elif self.index-pending['index']>self.expiry:
                status='expired';reason='超过固定观察窗口；不延长或重画旧候选'
            elif confirmed:
                status='confirmed';reason='后续收盘越过最近反向摆动，局部反转结构确认；不是MTR或趋势将持续的保证'
            else:continue
            out.append(self._event('three_push_wedge',original['direction'],bar,
                dict(original['anchors'],confirmation_level=pending['level'],invalidation_extreme=pending['extreme']),
                [reason,'不是买卖指令或实际成交'],context,status=status,parent_id=original['id'],
                candidate_observed_at=original['observed_at']))
            self.wedges.remove(pending)
        return out

    def update(self,bar,context,atr):
        if isinstance(atr,bool) or not isinstance(atr,(float,int)) or not math.isfinite(atr) or atr<=0:raise ValueError('atr must be finite positive')
        stream=(bar.symbol,bar.timeframe,bar.source)
        if self.stream is not None and stream!=self.stream:raise ValueError('mixed stream')
        if self.last:
            if bar.time==self.last.time:
                if bar==self.last:return []
                raise ValueError('revision rejected')
            if datetime.fromisoformat(bar.time)<datetime.fromisoformat(self.last.time):raise ValueError('out-of-order bar')
        self.stream=stream;self.index+=1
        out=self._attempts(bar,self.last,context) if self.last else []
        out+=self._wedge_lifecycle(bar,context)
        self.bars.append(bar)
        out+=self._wedge(bar,context,atr)
        self.last=bar
        return out
