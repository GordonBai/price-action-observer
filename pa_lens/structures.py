"""Causal context development, not official Brooks rules or trade instructions.

All thresholds here are explicit engineering proxies. Full MTR/final-flag and
measuring/exhaustion classifications remain subjective: events describe stages,
not a confirmed future reversal. Caller recreates this object on session/gaps.
"""
from collections import deque
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import hashlib
import json
import math

VERSION='structures/0.1'
NY=ZoneInfo('America/New_York')

class StructureDetector:
    def __init__(self,config=None):
        self.bars=deque(maxlen=90);self.index=-1;self.last=None;self.stream=None
        self.gaps=deque(maxlen=8);self.breakout=None;self.flag=None;self.flag_ended=-100
        self.tight_side=None;self.pivots={'low':deque(maxlen=2),'high':deque(maxlen=2)}
        self.line=None;self.line_episode=None
        self.opening=None;self.htf=[]

    def _event(self,family,status,direction,bar,ids,anchors,evidence,context,**extra):
        raw=[self.stream,VERSION,family,status,direction,bar.time,anchors]
        return {'id':hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()[:20],
                'family':family,'status':status,'direction':direction,'observed_at':bar.time,
                'confirmed_at':bar.time if status in ('confirmed','invalidated') else None,
                'anchors':anchors,'evidence':evidence,'knowledge_ids':ids,'context':context,
                'probability':None,'rule_version':VERSION,
                'uncertainty':'项目工程子集；阈值不是作者官方算法；局部条件成立不等于完整形态、未来方向或胜率。',
                'explanation':'结构发展观察：'+'；'.join(evidence)+'。不提供下单指令。',**extra}

    def _gaps(self,bar,prior,context):
        out=[]
        for g in list(self.gaps):
            age=self.index-g['index'];long=g['direction']=='long'
            filled=bar.low<=g['far_edge'] if long else bar.high>=g['far_edge']
            stage='expired' if age>15 else 'filled' if filled else 'held' if age==2 else None
            if stage:
                a={k:v for k,v in g.items() if k!='index'};a['stage']=stage
                out.append(self._event('gap_development','observed',g['direction'],bar,
                    ['measuring-vs-exhaustion','gap-taxonomy'],a,
                    [{'filled':'缺口远端已被触及；只确认回补，不能自动命名衰竭或反向趋势',
                      'held':'缺口在随后两根仍未完全回补；与延续相容，不是量度缺口定论',
                      'expired':'15根观察期结束；不再评价此缺口角色'}[stage]],context))
                if filled or age>15:self.gaps.remove(g)
        if len(prior)>=2:
            a,b=prior[-2:];span=b.high-b.low
            if span>0 and abs(b.close-b.open)/span>=.5:
                side='long' if bar.low>a.high and b.close>b.open else 'short' if bar.high<a.low and b.close<b.open else None
                if side:self.gaps.append({'direction':side,'created_at':bar.time,'before_time':a.time,'middle_time':b.time,'far_edge':a.high if side=='long' else a.low,'near_edge':bar.low if side=='long' else bar.high,'index':self.index})
        return out

    def _failed_failure(self,bar,prior,context):
        out=[];p=self.breakout
        if p:
            a={k:v for k,v in p.items() if k not in ('index','id','failed')}
            long=p['direction']=='long';outside=bar.close>p['level'] if long else bar.close<p['level']
            if self.index-p['index']>15:
                if p['failed']:out.append(self._event('failed_failure','expired',p['direction'],bar,['failed-failure'],a,['固定15根窗口到期，未见原突破恢复'],context,parent_id=p['id']))
                self.breakout=None
            elif not outside and not p['failed']:
                p['failure_time']=bar.time;p['failed']=True;a['failure_time']=bar.time
                e=self._event('failed_failure','candidate',p['direction'],bar,['failed-failure'],a,['原收盘突破后回到冻结区间；仅建立失败后的观察链，尚未恢复'],context)
                p['id']=e['id'];out.append(e)
            elif outside and p['failed']:
                out.append(self._event('failed_failure','confirmed',p['direction'],bar,['failed-failure','breakout-test'],a,['失败之后再次收在同一冻结突破位外；确认恢复条件，不保证延续'],context,parent_id=p['id']))
                self.breakout=None
        if self.breakout is None and len(prior)>=10:
            w=prior[-10:];hi=max(b.high for b in w);lo=min(b.low for b in w)
            overlap=sum(min(a.high,b.high)>max(a.low,b.low) for a,b in zip(w,w[1:]))/9
            side='long' if bar.close>hi else 'short' if bar.close<lo else None
            if side and overlap>=.6 and abs(w[-1].close-w[0].close)<=.6*(hi-lo):
                self.breakout={'direction':side,'level':hi if side=='long' else lo,'range_high':hi,'range_low':lo,'range_start':w[0].time,'range_end':w[-1].time,'original_breakout_time':bar.time,'index':self.index,'failed':False,'id':None}
        return out

    def _tight(self,bar,prior,context,atr):
        out=[];w=(prior+[bar])[-8:];side=None
        if len(w)==8:
            delta=w[-1].close-w[0].close
            sign=1 if delta>0 else -1
            progress=sum(sign*(b.close-a.close)>0 for a,b in zip(w,w[1:]))
            peak=sign*w[0].close;adverse=0
            for b in w:
                adverse=max(adverse,peak-sign*b.close);peak=max(peak,sign*b.close)
            extreme=sign*(w[0].high if sign>0 else w[0].low);wick_adverse=0
            for b in w:
                wick_adverse=max(wick_adverse,extreme-sign*(b.low if sign>0 else b.high))
                extreme=max(extreme,sign*(b.high if sign>0 else b.low))
            if abs(delta)>=2*atr and progress>=6 and adverse<=atr and wick_adverse<=2*atr:side='long' if sign>0 else 'short'
            if side and side!=self.tight_side:
                out.append(self._event('tight_channel','candidate',side,bar,['tight-channel'],
                    {'start':w[0].time,'end':bar.time,'bars':8,'directional_steps':progress,'net_change':delta,'max_adverse_close_move':adverse,'max_adverse_full_range':wick_adverse,'atr_at_observation':atr},
                    ['8根中至少6次同向收盘推进、净推进至少2 ATR、最大逆向收盘回撤不超1 ATR且全幅回撤不超2 ATR；只是紧通道代理，不计真实交易成本'],context))
        self.tight_side=side
        return out

    def _opening(self,bar,context):
        if bar.timeframe=="D":return []
        out=[];local=datetime.fromisoformat(bar.time).astimezone(NY);minutes=local.hour*60+local.minute-570
        if local.second or local.microsecond:self.opening=None;return []
        period=int(bar.timeframe)
        if self.index==0 and 0<minutes<=5 and minutes==period and local.weekday()<5:
            self.opening={'start':bar.time,'open':bar.open,'high':bar.high,'low':bar.low,'count':1,'range':None,'rejections':{},'bom':False,'reversal':None}
        p=self.opening
        if not p:return out
        if minutes>120:
            self.opening=None;return out
        if minutes<5:
            p['high']=max(p['high'],bar.high);p['low']=min(p['low'],bar.low);return out
        if p['range'] is None:
            if minutes!=5:self.opening=None;return out
            p['high']=max(p['high'],bar.high);p['low']=min(p['low'],bar.low)
            p['range']={'start':p['start'],'end':bar.time,'high':p['high'],'low':p['low'],'open':p['open'],'close':bar.close}
            return out
        if bar.high>p['high'] and bar.close<p['high']:p['rejections']['high']={'time':bar.time,'prior_intraday_high':p['high'],'high':bar.high,'close':bar.close}
        if bar.low<p['low'] and bar.close>p['low']:p['rejections']['low']={'time':bar.time,'prior_intraday_low':p['low'],'low':bar.low,'close':bar.close}
        if len(p['rejections'])==2 and not p['bom']:
            # One outside bar alone cannot establish the order of opposite tests.
            if p['rejections']['high']['time']!=p['rejections']['low']['time']:
                out.append(self._event('opening_breakout_mode','candidate','neutral',bar,['opening-breakout-mode'],{'opening_range':dict(p['range']),'tests':dict(p['rejections']),'window_minutes':120},['纽约09:30开盘覆盖完整；前两小时先后新日高/低后收回；双向模式候选，不是最终全天极值'],context));p['bom']=True
        r=p['range'];up=r['close']>r['open'];down=r['close']<r['open']
        reversed_=(up and bar.close<r['low']) or (down and bar.close>r['high'])
        if reversed_ and p['reversal'] is None:
            side='short' if up else 'long'
            e=self._event('opening_reversal','candidate',side,bar,['opening-reversal'],{'opening_range':dict(r),'elapsed_minutes':minutes},['首5分钟有收盘方向，后续收盘穿越其相反边界；仅开盘反向发展候选，不预测全天'],context)
            p['reversal']={'id':e['id'],'direction':side};out.append(e)
        elif p['reversal'] and not p['reversal'].get('done'):
            recovery=bar.close>r['high'] if up else bar.close<r['low']
            if recovery:
                out.append(self._event('opening_reversal','invalidated',p['reversal']['direction'],bar,['opening-reversal'],{'opening_range':dict(r)},['收盘恢复原开盘区间方向，先前反向候选失效'],context,parent_id=p['reversal']['id']));p['reversal']={'id':p['reversal']['id'],'direction':p['reversal']['direction'],'done':True}
        p['high']=max(p['high'],bar.high);p['low']=min(p['low'],bar.low)
        return out

    def _higher_timeframe(self,bar,context):
        if bar.timeframe!='1':return []
        local=datetime.fromisoformat(bar.time).astimezone(NY)
        minutes=local.hour*60+local.minute-570
        if local.second or local.microsecond:self.htf=[];return []
        if not 0<minutes<=390 or local.weekday()>=5:self.htf=[];return []
        slot=(minutes-1)%5
        if slot==0:self.htf=[bar]
        elif self.htf and len(self.htf)==slot and datetime.fromisoformat(bar.time)-datetime.fromisoformat(self.htf[-1].time)==timedelta(minutes=1):self.htf.append(bar)
        else:self.htf=[]
        if slot!=4 or len(self.htf)!=5:return []
        w=self.htf;self.htf=[]
        return [self._event('higher_timeframe_bar','observed','neutral',bar,['multi-timeframe'],
            {'timeframe_minutes':5,'component_bars':5,'first_component_close':w[0].time,'close_time':bar.time,'open':w[0].open,'high':max(b.high for b in w),'low':min(b.low for b in w),'close':bar.close,'volume':sum(b.volume for b in w)},
            ['纽约RTH对齐的完整5根一分钟条才形成5分钟OHLCV；未完成周期不发布，不据此宣称多周期一致'],context)]

    @staticmethod
    def _line_value(line,index):
        a,b=line['pivots']
        return b['price']+(index-b['index'])*(b['price']-a['price'])/(b['index']-a['index'])

    def _lines(self,bar,prior,context,atr):
        out=[];episode=self.line_episode
        if episode:
            line=episode['line'];value=self._line_value(line,self.index);long=line['direction']=='long'
            reclaimed=bar.close>value+atr if long else bar.close<value-atr
            if self.index-episode['index']>20 or reclaimed:
                out.append(self._event('mtr_development','expired' if not reclaimed else 'invalidated',
                    'short' if long else 'long',bar,['major-trend-reversal','trend-channel-lines'],
                    {'stage':'expired' if not reclaimed else 'line_reclaimed','line':line,'line_value':value},
                    ['趋势破坏后的局部发展窗口结束；不据此重写此前观察'],context,parent_id=episode['id']))
                self.line_episode=None
            elif episode.get('retest'):
                r=episode['retest'];confirmed=bar.close<r['low'] if long else bar.close>r['high']
                if confirmed:
                    out.append(self._event('mtr_development','candidate','short' if long else 'long',bar,
                        ['major-trend-reversal','trend-channel-lines'],
                        {'stage':'local_reversal_evidence','line':line,'line_value':value,'break_time':episode['break_time'],'retest':dict(r)},
                        ['冻结趋势线被破坏后回测，随后收盘越过回测条反向边界；只补充局部反转证据，未确认完整MTR'],context,parent_id=episode['id']))
                    self.line_episode=None
            else:
                touch=(bar.high>=value-atr*.25 and bar.close<=value) if long else (bar.low<=value+atr*.25 and bar.close>=value)
                if touch:
                    episode['retest']={'time':bar.time,'high':bar.high,'low':bar.low,'close':bar.close,'line_value':value}
                    out.append(self._event('trend_line_retest','observed','short' if long else 'long',bar,
                        ['trend-channel-lines','major-trend-reversal'],
                        {'line':line,'line_value':value,'break_time':episode['break_time'],'tolerance_atr':.25},
                        ['破线后后续条回到冻结线0.25 ATR以内并收在破线侧；不是已完成大反转'],context,parent_id=episode['id']))
        elif self.line:
            line=self.line;value=self._line_value(line,self.index);long=line['direction']=='long'
            broken=bar.close<value if long else bar.close>value
            if broken:
                a={'stage':'trend_line_broken','line':line,'line_value':value}
                e=self._event('mtr_development','candidate','short' if long else 'long',bar,
                    ['major-trend-reversal','trend-channel-lines'],a,
                    ['收盘越过此前冻结的两摆点趋势线；MTR发展候选起点，仍可能只是回调或区间'],context)
                self.line_episode={'line':line,'index':self.index,'break_time':bar.time,'id':e['id']};out.append(e);self.line=None
        # Confirm the centre pivot at this bar close. Never draw a usable line
        # before both anchors have their right-side confirmations.
        w=(prior+[bar])[-5:]
        if len(w)<5:return out
        center=w[2];neighbors=[w[i] for i in (0,1,3,4)]
        is_low=all(center.low<b.low for b in neighbors);is_high=all(center.high>b.high for b in neighbors)
        if is_low==is_high:return out
        kind='low' if is_low else 'high';p={'price':getattr(center,kind),'index':self.index-2,'time':center.time,'confirmed_at':bar.time}
        self.pivots[kind].append(p)
        if len(self.pivots[kind])<2 or self.line_episode:return out
        a,b=self.pivots[kind];side='long' if kind=='low' else 'short'
        directed=b['price']>a['price'] if kind=='low' else b['price']<a['price']
        if not directed or b['index']-a['index']>40:return out
        if context!=('trend_up' if side=='long' else 'trend_down'):return out
        line={'direction':side,'pivots':[dict(a),dict(b)],'frozen_at':bar.time,'anchor_kind':kind}
        self.line=line
        out.append(self._event('trend_line','observed',side,bar,['trend-channel-lines'],line,
            ['两已右侧确认摆点定义方向趋势线；本时刻冻结此版本，未来重新选点不改写历史版本'],context))
        return out

    def _flags(self,bar,prior,context,atr):
        out=[];p=self.flag
        if p:
            long=p['direction']=='long';a={k:v for k,v in p.items() if k not in ('id','index','broken')}
            outside=bar.close>p['high'] if long else bar.close<p['low']
            opposite=bar.close<p['low'] if long else bar.close>p['high']
            if self.index-p['index']>15:
                a['stage']='expired';out.append(self._event('final_flag_development','expired',p['direction'],bar,['final-flag'],a,['固定15根观察窗口到期，不能判断为最后旗形'],context,parent_id=p['id']));self.flag=None;self.flag_ended=self.index
            elif p['broken'] and not outside:
                a['stage']='breakout_failed';out.append(self._event('final_flag_development','candidate','short' if long else 'long',bar,['final-flag'],a,['晚期盘整同向突破后收回原旗形；支持末旗假设但不是最终反转定论'],context,parent_id=p['id']));self.flag=None;self.flag_ended=self.index
            elif not p['broken'] and outside:
                p['broken']=True;p['breakout_time']=bar.time;a['breakout_time']=bar.time;a['stage']='continuation_breakout'
                out.append(self._event('final_flag_development','candidate',p['direction'],bar,['final-flag'],a,['盘整向原趋势突破，尚不知道它是最后延续还是有效持续'],context,parent_id=p['id']))
            elif opposite:
                a['stage']='opposite_break';out.append(self._event('final_flag_development','invalidated',p['direction'],bar,['final-flag'],a,['未发生同向延续突破就向相反方向离开；本版末旗过程不成立'],context,parent_id=p['id']));self.flag=None;self.flag_ended=self.index
        if self.flag is not None or self.index-self.flag_ended<5:return out
        w=(prior+[bar])[-15:]
        if len(w)<15:return out
        trend,flag=w[:10],w[10:]
        delta=trend[-1].close-trend[0].close
        path=sum(abs(b.close-a.close) for a,b in zip(trend,trend[1:]))
        hi=max(b.high for b in flag);lo=min(b.low for b in flag)
        overlap=sum(min(a.high,b.high)>max(a.low,b.low) for a,b in zip(flag,flag[1:]))/4
        side='long' if delta>0 else 'short'
        if context!=('trend_up' if side=='long' else 'trend_down') or not path:return out
        if abs(delta)<2*atr or abs(delta)/path<.7 or hi-lo>2*atr or overlap<.75 or abs(flag[-1].close-flag[0].close)>.5*(hi-lo):return out
        p={'direction':side,'trend_start':trend[0].time,'trend_end':trend[-1].time,'flag_start':flag[0].time,'flag_end':bar.time,'high':hi,'low':lo,'index':self.index,'broken':False}
        a={k:v for k,v in p.items() if k not in ('index','broken')};a['stage']='late_consolidation'
        e=self._event('final_flag_development','candidate',side,bar,['final-flag'],a,['10根方向推进后5根紧盘整；仅晚期盘整代理，尚未知道是否末旗'],context)
        p['id']=e['id'];self.flag=p;out.append(e)
        return out

    def update(self,bar,context,atr):
        if isinstance(atr,bool) or not isinstance(atr,(int,float)) or not math.isfinite(atr) or atr<=0:raise ValueError('atr must be finite positive')
        stream=(bar.symbol,bar.timeframe,bar.source)
        if self.stream is not None and self.stream!=stream:raise ValueError('mixed stream')
        if self.last:
            if bar.time==self.last.time:
                if bar==self.last:return []
                raise ValueError('revision rejected')
            if datetime.fromisoformat(bar.time)<datetime.fromisoformat(self.last.time):raise ValueError('out-of-order bar')
        self.stream=stream;self.index+=1;prior=list(self.bars)
        out=self._gaps(bar,prior,context)+self._failed_failure(bar,prior,context)+self._tight(bar,prior,context,atr)+self._opening(bar,context)+self._higher_timeframe(bar,context)+self._lines(bar,prior,context,atr)+self._flags(bar,prior,context,atr)
        self.bars.append(bar);self.last=bar
        return out
