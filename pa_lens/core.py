"""Deterministic closed-bar rules. Thresholds are engineering heuristics, not Brooks algorithms."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
import math
from .advanced import AdvancedDetector
from .observations import ObservationDetector
from .explanations import ground_event, KNOWLEDGE_VERSION

ENGINE_VERSION = "0.3.0"


def parse_time(value):
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('time must have a timezone')
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class Bar:
    symbol: str
    timeframe: str
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    source: str = 'manual'

    def __post_init__(self):
        object.__setattr__(self, 'time', parse_time(self.time).isoformat())
        for name in ('open', 'high', 'low', 'close', 'volume'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{name} must be a finite number')
        if self.low <= 0 or self.high < max(self.open,self.low,self.close) or self.low > min(self.open,self.close) or self.volume < 0:
            raise ValueError('invalid OHLCV')
        if not isinstance(self.timeframe,str) or not self.timeframe.isdigit() or not 1 <= int(self.timeframe) <= 240:
            raise ValueError('only 1..240 minute timeframes supported')
        if any(not isinstance(v,str) or not v or len(v)>100 for v in (self.symbol,self.source)):
            raise ValueError('invalid symbol/source')

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data,dict): raise ValueError('bar must be an object')
        if data.get('final',True) is not True: raise ValueError('only final closed bars accepted')
        keys=cls.__dataclass_fields__
        try: return cls(**{k:data[k] for k in keys if k in data})
        except TypeError as ex: raise ValueError('missing or invalid bar fields') from ex


@dataclass(frozen=True)
class Config:
    pivot_left: int = 2
    pivot_right: int = 2
    min_separation: int = 3
    tolerance_atr: float = .6
    min_rebound_atr: float = 1.0
    range_window: int = 20
    min_history: int = 5
    tick: float = .01
    setup_expiry: int = 20
    max_pattern_bars: int = 60

    def __post_init__(self):
        for name in ('pivot_left','pivot_right','min_separation','range_window','min_history','setup_expiry','max_pattern_bars'):
            if isinstance(getattr(self,name),bool) or not isinstance(getattr(self,name),int) or getattr(self,name)<1: raise ValueError(f'invalid {name}')
        for name in ('tolerance_atr','min_rebound_atr','tick'):
            v=getattr(self,name)
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0: raise ValueError(f'invalid {name}')


class Engine:
    def __init__(self,config=None):
        self.config=config or Config()
        self.config_hash=hashlib.sha256(json.dumps(asdict(self.config),sort_keys=True).encode()).hexdigest()[:12]
        self.stream=None
        self.last=None
        self.bars=[]
        self.pivots={'low':[],'high':[]}
        self.pending=[]
        self.projections=[]
        self.events=[]
        self._batch=[]
        self.total_bars=0
        self.gap_count=0
        self._range_latch=None
        self.advanced=AdvancedDetector(self.config)
        self.observations=ObservationDetector(self.config)
        self._detector_parents={}

    def _emit(self,family,status,direction,bar,anchors=None,evidence=None,**values):
        anchors=anchors or {}
        raw=[self.stream,bar.time,family,status,direction,anchors,self.config_hash,ENGINE_VERSION]
        event={'id':hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()[:20],
               'family':family,'status':status,'direction':direction,'observed_at':bar.time,
               'confirmed_at':bar.time if status in ('confirmed','reached','invalidated') else None,
               'anchors':anchors,'evidence':evidence or [],'probability':None,
               'rule_version':'pa-lens/'+ENGINE_VERSION,'config_hash':self.config_hash,**values}
        words={'double_bottom':'双底','double_top':'双顶','range_breakout':'区间突破',
               'measured_move':'等幅投射','inside_bar':'内包K线','outside_bar':'外包K线',
               'data_gap':'行情缺口','session_reset':'会话重置'}
        states={'candidate':'候选，尚未确认突破','confirmed':'结构收盘确认；不预测未来方向',
                'invalidated':'已失效','expired':'已过期','reached':'目标触及，不代表反转','observed':'已观察'}
        event['explanation']=f"{words.get(family,family)}：{states.get(status,status)}。"+'；'.join(event['evidence'])
        ground_event(event)
        self.events.append(event)
        if len(self.events)>500: del self.events[:-500]
        self._batch.append(event)
        return event

    def _reset(self):
        self.bars=[]; self.pivots={'low':[],'high':[]};self.pending=[];self.projections=[];self._range_latch=None
        self.advanced=AdvancedDetector(self.config)
        self.observations=ObservationDetector(self.config)
        self._detector_parents={}

    def _atr(self):
        bars=self.bars[-15:]
        tr=[max(b.high-b.low,abs(b.high-bars[i-1].close),abs(b.low-bars[i-1].close)) if i else b.high-b.low for i,b in enumerate(bars)]
        return max(sum(tr)/len(tr),self.config.tick)

    def _context(self):
        if len(self.bars)<self.config.min_history:return 'warmup'
        bs=self.bars[-20:]
        path=sum(abs(b.close-a.close) for a,b in zip(bs,bs[1:]))
        displacement=bs[-1].close-bs[0].close
        efficiency=abs(displacement)/path if path else 0
        if efficiency>.55:return 'trend_up' if displacement>0 else 'trend_down'
        return 'range_or_transition'

    def update(self,bar):
        if not isinstance(bar,Bar):raise ValueError('expected Bar')
        key=(bar.symbol,bar.timeframe,bar.source)
        if self.stream is not None and key!=self.stream:raise ValueError('mixed stream; use separate Engine')
        if self.last:
            if parse_time(bar.time)<parse_time(self.last.time):raise ValueError('out-of-order bar')
            if bar.time==self.last.time:
                if bar==self.last:return []
                raise ValueError('bar revision rejected; rebuild explicitly')
        self._batch=[]
        self.stream=key
        if self.last:
            old=parse_time(self.last.time);new=parse_time(bar.time)
            if old.astimezone(ZoneInfo('America/New_York')).date()!=new.astimezone(ZoneInfo('America/New_York')).date():
                self._reset();self._emit('session_reset','observed','neutral',bar,evidence=['跨交易所本地日期，重置形态；不跨日连线'])
            elif (new-old).total_seconds()!=int(bar.timeframe)*60:
                self.gap_count+=1;self._reset();self._emit('data_gap','observed','neutral',bar,evidence=['时间间隔不连续，重置形态；未补造价格'])
        self.last=bar;self.total_bars+=1;self.bars.append(bar)
        i=len(self.bars)-1;c=self.config;atr=self._atr()
        if i:
            prev=self.bars[-2]
            if bar.high<prev.high and bar.low>prev.low:self._emit('inside_bar','observed','neutral',bar)
            if bar.high>prev.high and bar.low<prev.low:self._emit('outside_bar','observed','neutral',bar)
        # Previously generated targets may be touched now, never on their creation bar.
        for p in self.projections[:]:
            invalid = (p['direction']=='long' and bar.low<=p['stop']) or (p['direction']=='short' and bar.high>=p['stop'])
            if invalid:
                self._emit('measured_move','invalidated',p['direction'],bar,p['anchors'],['结构失效，停止跟踪此场景目标；同根路径未知时保守失效优先'],parent_id=p['id'],target=p['target'])
                self.projections.remove(p);continue
            if (p['direction']=='long' and bar.high>=p['target']) or (p['direction']=='short' and bar.low<=p['target']):
                self._emit('measured_move','reached',p['direction'],bar,p['anchors'],['目标触及不是反向入场依据'],target=p['target'],parent_id=p['id'])
                self.projections.remove(p)
        # Confirm a pivot only after all right-side bars have closed.
        idx=i-c.pivot_right
        if idx>=c.pivot_left:
            b=self.bars[idx];neighbors=self.bars[idx-c.pivot_left:idx]+self.bars[idx+1:i+1]
            for kind in ('low','high'):
                value=getattr(b,kind)
                match=all(value<getattr(n,kind) for n in neighbors) if kind=='low' else all(value>getattr(n,kind) for n in neighbors)
                if not match:continue
                pivot={'index':idx,'price':value,'time':b.time,'confirmed_at':bar.time}
                previous=self.pivots[kind][-1] if self.pivots[kind] else None
                self.pivots[kind].append(pivot)
                if previous and c.min_separation<=idx-previous['index']<=c.max_pattern_bars and abs(value-previous['price'])<=c.tolerance_atr*atr:
                    between=self.bars[previous['index']+1:idx]
                    neckline=max(x.high for x in between) if kind=='low' else min(x.low for x in between)
                    extreme=min(value,previous['price']) if kind=='low' else max(value,previous['price'])
                    height=abs(neckline-extreme)
                    if height<c.min_rebound_atr*atr:continue
                    direction='long' if kind=='low' else 'short';family='double_bottom' if kind=='low' else 'double_top'
                    anchors={'first_time':previous['time'],'first':previous['price'],'second_time':b.time,'second':value,'neckline':neckline,'height':height,'pivot_confirmed_at':bar.time}
                    event=self._emit(family,'candidate',direction,bar,anchors,['摆动点已确认；容差为工程近似','颈线突破是严格版本，不覆盖所有Brooks双底/顶'],context=self._context())
                    self.pending.append({'family':family,'direction':direction,'anchors':anchors,'index':i,'id':event['id'],'extreme':extreme})
        for p in self.pending[:]:
            direction=p['direction'];long=direction=='long';neck=p['anchors']['neckline']
            if (long and bar.low<p['extreme']-c.tick) or (not long and bar.high>p['extreme']+c.tick):
                self._emit(p['family'],'invalidated',direction,bar,p['anchors'],['先触及结构失效位；保守取消'],parent_id=p['id']);self.pending.remove(p)
            elif i-p['index']>c.setup_expiry:
                self._emit(p['family'],'expired',direction,bar,p['anchors'],parent_id=p['id']);self.pending.remove(p)
            elif (long and bar.close>neck) or (not long and bar.close<neck):
                trigger=bar.high+c.tick if long else bar.low-c.tick
                stop=p['extreme']-c.tick if long else p['extreme']+c.tick
                target=neck+p['anchors']['height'] if long else neck-p['anchors']['height']
                event=self._emit(p['family'],'confirmed',direction,bar,p['anchors'],['收盘越过颈线；仅确认结构条件','投射是参考场景，不是价格必须到达的目标'],
                                 trigger=trigger,stop=stop,target=target,parent_id=p['id'],context=self._context())
                since_second=[b for b in self.bars if b.time>=p['anchors']['second_time']]
                touched=any(b.high>=target if long else b.low<=target for b in since_second)
                event['target_state_at_creation']='already_touched' if touched else 'pending'
                if touched:
                    event['evidence'].append('投射目标在确认前或本根已触及，不作为新增目标跟踪')
                    event['explanation']+='；投射目标已触及，不是新的预测目标。'
                else:self.projections.append(event)
                self.pending.remove(p)
        if i>=c.range_window:
            window=self.bars[-c.range_window-1:-1];hi=max(b.high for b in window);lo=min(b.low for b in window)
            # Restrict breakout reference to two-sided overlapping ranges, not every rolling high.
            displacement=abs(window[-1].close-window[0].close)
            overlap=sum(min(a.high,b.high)>max(a.low,b.low) for a,b in zip(window,window[1:]))/max(1,len(window)-1)
            direction='long' if bar.close>hi else 'short' if bar.close<lo else None
            if direction and overlap>=.6 and displacement<=.6*(hi-lo) and self._range_latch!=direction:
                anchors={'high':hi,'low':lo,'start':window[0].time,'end':window[-1].time,'type':'range_height'}
                target=hi+(hi-lo) if direction=='long' else lo-(hi-lo)
                event=self._emit('range_breakout','confirmed',direction,bar,anchors,['突破前区间已冻结；目标为区间高度投射','滚动区间是工程近似，可能假突破'],target=target,
                                 trigger=bar.high+c.tick if direction=='long' else bar.low-c.tick,stop=lo-c.tick if direction=='long' else hi+c.tick,context=self._context())
                touched=bar.high>=target if direction=='long' else bar.low<=target
                event['target_state_at_creation']='already_touched' if touched else 'pending'
                if touched:
                    event['evidence'].append('投射目标在本根已触及，不作为新增目标跟踪')
                    event['explanation']+='；投射目标已触及，不是新的预测目标。'
                else:self.projections.append(event)
                self._range_latch=direction
            elif not direction:self._range_latch=None
        for a in self.advanced.update(bar,self._context(),atr)+self.observations.update(bar,self._context(),atr):
            extras={k:v for k,v in a.items() if k not in ('id','family','status','direction','observed_at','confirmed_at','anchors','evidence','probability','rule_version','explanation')}
            if extras.get('parent_id'):
                extras['parent_id']=self._detector_parents.pop(extras['parent_id'],extras['parent_id'])
            event=self._emit(a['family'],a['status'],a['direction'],bar,a['anchors'],a['evidence'],advanced_rule_version=a['rule_version'],**extras)
            event['explanation']=a['explanation']
            if a['family']=='three_push_wedge' and a['status']=='candidate':
                self._detector_parents[a['id']]=event['id']
                while len(self._detector_parents)>20:self._detector_parents.pop(next(iter(self._detector_parents)))
        return list(self._batch)

    def snapshot(self):
        return {'schema':'pa-lens/snapshot-v1','stream':self.stream,'last_bar':asdict(self.last) if self.last else None,
                'bars_in_segment':len(self.bars),'total_bars':self.total_bars,'gap_count':self.gap_count,
                'context':self._context(),'config':asdict(self.config),'config_hash':self.config_hash,
                'events':self.events[-100:],'recent_bars':[asdict(b) for b in self.bars[-120:]],
                'probability':None,'mode':'research_only','purpose':'pattern_observation_and_explanation',
                'knowledge_version':KNOWLEDGE_VERSION,'coverage':'partial_engineering_approximations'}


def project_equal_leg(a,b,c):
    """Manual frozen-anchor AB=CD projection; anchor selection is NOT automated."""
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in (a,b,c)):
        raise ValueError('anchors must be positive finite prices')
    target=c+(b-a)
    return {'type':'equal_leg','anchors':{'a':a,'b':b,'c':c},'target':target,
            'probability':None,'note':'人工指定锚点的等长腿投射；不是自动入场或必达目标'}
