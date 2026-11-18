"""Closed-bar descriptive observations, not a trading policy.

All constants below are versioned engineering approximations, not calibrated
Brooks definitions. EMA20 is seeded by the first close; its observations begin
only after 20 bars. Caller must recreate this detector on session/data gaps.
Retained history is at most 32 bars; one frozen breakout scenario expires after
10 bars. No target, entry, fill, profitability or win-probability is inferred.
"""
from collections import deque
from datetime import datetime
import hashlib
import json
import math

VERSION='observations/0.1'

class ObservationDetector:
    def __init__(self,config=None):
        self.bars=deque(maxlen=32)
        self.last=None
        self.stream=None
        self.index=-1
        self.ema=None
        self.ema_side=None
        self.ema_run=0
        self.micro={'long':1,'short':1}
        self.pending=None
        self.range_active=False
        self.barbwire_active=False
        self.tick=getattr(config,'tick',.01)

    @staticmethod
    def _inside(a,b):
        return a.high<b.high and a.low>b.low

    @staticmethod
    def _outside(a,b):
        return a.high>b.high and a.low<b.low

    def update(self,bar,context,atr):
        if isinstance(atr,bool) or not isinstance(atr,(int,float)) or not math.isfinite(atr) or atr<=0:
            raise ValueError('atr must be finite positive')
        stream=(bar.symbol,bar.timeframe,bar.source)
        if self.stream is not None and stream!=self.stream:raise ValueError('mixed stream')
        if self.last:
            if bar.time==self.last.time:
                if bar==self.last:return []
                raise ValueError('revision rejected')
            if datetime.fromisoformat(bar.time)<datetime.fromisoformat(self.last.time):raise ValueError('out-of-order bar')
        self.stream=stream;self.index+=1
        out=[];prior=list(self.bars);prev=self.last
        span=bar.high-bar.low
        body=abs(bar.close-bar.open)
        ratio=body/span if span else 0
        close_pos=(bar.close-bar.low)/span if span else .5
        direction='long' if bar.close>bar.open else 'short' if bar.close<bar.open else 'neutral'
        metrics={'bar_time':bar.time,'open':bar.open,'high':bar.high,'low':bar.low,'close':bar.close,'body_fraction':ratio,'close_position':close_pos}
        def emit(family,status,side,ids,anchors,evidence):
            raw=[stream,VERSION,bar.time,family,status,side,anchors]
            out.append({'id':hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()[:20],
                'family':family,'status':status,'direction':side,'observed_at':bar.time,
                'confirmed_at':bar.time if status in ('confirmed','invalidated') else None,
                'anchors':anchors,'evidence':evidence,'knowledge_ids':ids,'context':context,
                'probability':None,'rule_version':VERSION,
                'explanation':'工程近似观察：'+'；'.join(evidence)+'。不代表交易指令、必然反转或已验证胜率。'})
        if ratio<=.2:
            emit('doji','observed','neutral',['candle-body-vs-range'],metrics,['十字/小实体：实体占全幅不超过20%；没有单独方向结论'])
        if ratio>=.65 and ((direction=='long' and close_pos>=.8) or (direction=='short' and close_pos<=.2)):
            emit('trend_bar','observed',direction,['candle-body-vs-range','buying-pressure'],metrics,['趋势条：实体至少65%，收盘靠近方向端20%区域；只描述本根强度'])
        lower=min(bar.open,bar.close)-bar.low;upper=bar.high-max(bar.open,bar.close)
        if span and lower/span>=.5 and close_pos>=.7:
            emit('reversal_bar','candidate','long',['signal-entry-stop'],metrics,['长下影至少全幅50%，收盘位于上部30%；只构成反转条候选，须结合前趋势'])
        if span and upper/span>=.5 and close_pos<=.3:
            emit('reversal_bar','candidate','short',['signal-entry-stop'],metrics,['长上影至少全幅50%，收盘位于下部30%；只构成反转条候选，须结合前趋势'])
        if prev:
            if abs(bar.open-prev.close)>=self.tick:
                emit('gap_open','observed','long' if bar.open>prev.close else 'short',['gap-open','gap-taxonomy'],{'previous_close':prev.close,'current_open':bar.open,'previous_time':prev.time,'gap':bar.open-prev.close},['相邻条开盘与前收不同；不等于整根区间不重叠，也不推断收盘方向'])
            blo,bhi=sorted((bar.open,bar.close));plo,phi=sorted((prev.open,prev.close))
            if blo>phi or bhi<plo:
                emit('body_gap','observed','long' if blo>phi else 'short',['body-gap'],{'previous_body':[plo,phi],'current_body':[blo,bhi],'previous_time':prev.time},['相邻实体严格不重叠；影线是否交叠是另一事实'])
            for side in ('long','short'):
                # A shrinking inside sequence can raise lows AND lower highs.
                # Require both boundaries and closes to advance in one direction;
                # this is a deliberately strict subset, not all Brooks microchannels.
                follows=(bar.low>prev.low and bar.high>prev.high and bar.close>=prev.close) if side=='long' else (bar.high<prev.high and bar.low<prev.low and bar.close<=prev.close)
                self.micro[side]=self.micro[side]+1 if follows else 1
                if self.micro[side]>=4:
                    emit('micro_channel','observed',side,['micro-channel'],{'bars':self.micro[side],'last_extreme':bar.low if side=='long' else bar.high},['严格工程微通道：至少4条高低点同向推进且收盘不逆向；排除内包压缩，仅覆盖微通道严格子集'])
        if len(prior)>=2:
            a,b=prior[-2:]
            if self._inside(b,a) and self._inside(bar,b):
                emit('ii','candidate','neutral',['inside-sequences'],{'times':[a.time,b.time,bar.time],'high':bar.high,'low':bar.low},['连续两次严格全幅内包；双向突破候选，不预判方向'])
            middle_ratio=abs(b.close-b.open)/(b.high-b.low) if b.high>b.low else 0
            if middle_ratio>=.5 and ((bar.low>a.high and b.close>b.open) or (bar.high<a.low and b.close<b.open)):
                emit('micro_gap','observed','long' if bar.low>a.high else 'short',['micro-gap'],{'before_time':a.time,'middle_time':b.time,'after_time':bar.time,'before_range':[a.low,a.high],'after_range':[bar.low,bar.high]},['中间条实体至少50%且同向，隔一根的高低范围严格不重叠；只在第三根收盘可观察'])
        if len(prior)>=3:
            a,b,c=prior[-3:]
            if self._inside(b,a) and self._outside(c,b) and self._inside(bar,c):
                emit('ioi','candidate','neutral',['inside-sequences'],{'times':[a.time,b.time,c.time,bar.time],'high':c.high,'low':c.low},['严格内包/外包/内包序列；使用四根检验，尚未选择突破方向'])
        recent=(prior+[bar])[-8:]
        if len(recent)==8:
            overlap=sum(min(a.high,b.high)>max(a.low,b.low) for a,b in zip(recent,recent[1:]))/7
            width=max(b.high for b in recent)-min(b.low for b in recent)
            tight=overlap>=.85 and width<=2.5*atr
            has_doji=any(abs(b.close-b.open)<=.2*(b.high-b.low) for b in recent)
            anchors={'start':recent[0].time,'end':bar.time,'bars':8,'overlap_fraction':overlap,'width':width,'atr':atr,'width_atr_limit':2.5}
            if tight and not self.range_active:
                emit('tight_trading_range','candidate','neutral',['tight-trading-range'],anchors,['8条中相邻重叠至少85%，总幅不超过2.5 ATR；紧区间工程候选'])
            if tight and has_doji and not self.barbwire_active:
                emit('barbwire','candidate','neutral',['tight-trading-range'],anchors,['紧区间候选内至少一根小实体条；铁丝网是子类，不是全部紧区间的同义词'])
            self.range_active=tight;self.barbwire_active=tight and has_doji
        if len(prior)>=10:
            avg=sum(b.high-b.low for b in prior[-10:])/10
            if avg and span>=2*avg and ratio>=.65:
                anchors={**metrics,'previous_10_mean_range':avg,'range_multiple':span/avg}
                emit('surprise_bar','observed',direction,['surprise-bar'],anchors,['全幅至少此前10条均幅2倍且实体至少65%；异常条角色尚未确定'])
                if (context=='trend_up' and direction=='long') or (context=='trend_down' and direction=='short'):
                    emit('climax','candidate',direction,['climax'],anchors,['方向性语境中出现异常扩幅；高潮仅为候选，也可能是趋势延续'])
        self.ema=bar.close if self.ema is None else self.ema+(2/21)*(bar.close-self.ema)
        if self.index>=19:
            side='long' if bar.low>self.ema else 'short' if bar.high<self.ema else None
            if side:
                self.ema_run=self.ema_run+1 if self.ema_side==side else 1
                self.ema_side=side
                if self.ema_run==2:
                    emit('ema_gap','observed',side,['gap-taxonomy','support-resistance'],{'ema20':self.ema,'bars_without_touch':2},['连续两根全幅位于当根EMA20同侧；均线由首收盘递推，20条后开始观察'])
            else:
                if self.ema_run>=10:
                    emit('ema_first_return','observed',self.ema_side,['support-resistance','micro-channel'],{'ema20':self.ema,'preceding_separated_bars':self.ema_run},['至少10根与当根EMA分离后首次触及；不是自动反转或支撑有效的证明'])
                self.ema_side=None;self.ema_run=0
        # A frozen range breakout is kept for ten subsequent bars, not retuned.
        pending=self.pending
        if pending:
            long=pending['direction']=='long';level=pending['level'];age=self.index-pending['index']
            anchors={k:v for k,v in pending.items() if k!='index'}
            inside=bar.close<=level if long else bar.close>=level
            if age>10:self.pending=None
            elif inside:
                emit('failed_breakout','confirmed',pending['direction'],['breakout-follow-through','premise-failure-management'],anchors,['收盘回到冻结突破位内侧；确认的是回落事实，不预测反向趋势'])
                self.pending=None
            else:
                if age==1:
                    good=(bar.close>pending['close'] and bar.close>bar.open) if long else (bar.close<pending['close'] and bar.close<bar.open)
                    emit('breakout_follow_through','confirmed' if good else 'observed',pending['direction'],['breakout-follow-through'],{**anchors,'quality':'directional' if good else 'weak'},['下一根方向性收盘推进' if good else '下一根缺少方向性收盘推进；弱跟随不等于失败'])
                touch=bar.low<=level if long else bar.high>=level
                retrace=(bar.low<prev.low and bar.close<prev.close) if long else (bar.high>prev.high and bar.close>prev.close)
                if (touch or retrace) and not pending.get('tested'):
                    emit('breakout_test','observed',pending['direction'],['breakout-test','pullback-flag'],{**anchors,'test_type':'touched_and_reclaimed' if touch else 'space_preserved','remaining_space':(bar.low-level if long else level-bar.high)},['触及冻结突破位后收在外侧；与保持缺口的回测分别记录' if touch else '回撤低/高点与收盘同时逆向，但全幅仍在冻结突破位之外；缺口仍保持'])
                    pending['tested']=True
        if self.pending is None and len(prior)>=10:
            window=prior[-10:];hi=max(b.high for b in window);lo=min(b.low for b in window)
            overlap=sum(min(a.high,b.high)>max(a.low,b.low) for a,b in zip(window,window[1:]))/9
            displacement=abs(window[-1].close-window[0].close)
            side='long' if bar.close>hi else 'short' if bar.close<lo else None
            if side and overlap>=.6 and displacement<=.6*(hi-lo):
                self.pending={'direction':side,'level':hi if side=='long' else lo,'range_high':hi,'range_low':lo,'range_start':window[0].time,'range_end':window[-1].time,'breakout_time':bar.time,'close':bar.close,'index':self.index}
                emit('breakout_observation','confirmed',side,['breakout-follow-through'],{k:v for k,v in self.pending.items() if k!='index'},['收盘突破此前10条双向重叠区间；参考区间已冻结，跟随尚未知'])
        self.bars.append(bar);self.last=bar
        return out
