"""Structured terminal setup, not natural-language parsing or credential handling."""
from datetime import datetime,timezone
from pathlib import Path
import re
import shlex
import sys
from .robinhood import _symbols

PERIODS={'1m':'minute','5m':'5minute','10m':'10minute','15m':'15minute','30m':'30minute','1h':'hour','4h':'4hour','1d':'day','day':'day'}
BOUNDS=('regular','extended','trading','24_5','24_7','hyper_trading')

class Cancelled(Exception):pass


def run_wizard(runner, *, input_stream=None, output_stream=None):
    """Collect validated choices; runner receives argv only after explicit confirmation."""
    inp=input_stream or sys.stdin;out=output_stream or sys.stdout
    if not inp.isatty() or not out.isatty():
        raise ValueError('启动向导需要交互式 TTY；脚本/管道请直接使用 poll-robinhood --count N --output jsonl')
    def write(text):out.write(text+'\n');out.flush()
    def ask(label,default,validator):
        while True:
            out.write(label+(f' [{default}]' if default else '')+': ');out.flush()
            line=inp.readline()
            if not line:raise Cancelled()
            value=line.strip()
            if value.lower() in ('q','quit','cancel','取消'):raise Cancelled()
            value=value or default
            try:return validator(value)
            except (ValueError,TypeError) as exc:write('输入无效：'+str(exc))
    def choice(options):
        def parse(value):
            value=value.lower()
            if value not in options:raise ValueError('请选择 '+', '.join(options))
            return value
        return parse
    def integer(low,high):
        def parse(value):
            if not re.fullmatch(r'[0-9]+',value):raise ValueError(f'请输入整数 {low}..{high}')
            n=int(value)
            if not low<=n<=high:raise ValueError(f'范围 {low}..{high}')
            return n
        return parse
    def symbols(value):
        values=[v.upper() for v in re.split(r'[\s,]+',value.strip()) if v]
        if len(values)>10:raise ValueError('一次最多10只股票')
        return list(_symbols(values))
    def period(value):
        value=value.lower()
        if value in PERIODS:return PERIODS[value]
        if value in PERIODS.values():return value
        raise ValueError('周期：1m/5m/10m/15m/30m/1h/4h/1d')
    def infra(value):
        path=Path(value).expanduser().resolve()
        if not (path/'src/trading_execution/transport.py').is_file():
            raise ValueError('此路径应包含 src/trading_execution/transport.py；向导不安装软件或读取凭据')
        return str(path)
    def db(value):
        if value==':memory:':raise ValueError('监控需要持久日志，请使用文件路径')
        path=Path(value).expanduser()
        if path.exists():raise ValueError('为避免规则身份冲突或另一进程占用，请在向导使用新日志文件；复用请直接运行CLI')
        if any(ord(c)<32 for c in str(path)):raise ValueError('日志路径不能包含控制字符')
        return str(path)
    write('PA Observer 启动向导 · 只读行情，不交易、不输入密码。任意步骤输入 q 取消。')
    try:
        names=ask('股票（空格或逗号分隔，最多10只）','NVDA',symbols)
        interval=ask('K线周期 1m/5m/10m/15m/30m/1h/4h/1d','5m',period)
        if interval in ('15minute','day'):
            write('该周期仅支持 regular。15m为完整3×5m聚合；没有原生15m指标。' if interval=='15minute' else '日线仅regular；时间为下一UTC午夜的保守可知时刻。')
            bounds='regular'
        else:bounds=ask('市场时段 regular/extended/trading/24_5/24_7/hyper_trading','regular',choice(BOUNDS))
        mode=ask('调度 fixed（固定秒数）/ close（收盘边界对齐）','fixed',choice(('fixed','close')))
        seconds=ask('每轮完成后等待秒数','30',integer(5,3600)) if mode=='fixed' else 30
        settle=ask('收盘边界后等待秒数','10',integer(0,300)) if mode=='close' else None
        def rounds(value):return None if value.lower()=='infinite' else integer(1,10000)(value)
        count=ask('运行轮数 1..10000；无限请输入 infinite（Ctrl-C停止）','10',rounds)
        write('严格模式排除插值标记缺失的数据；探索UNKNOWN仍是未知质量、ready=false，不是可靠交易信号。')
        quality=ask('允许探索UNKNOWN？输入 y 明确允许；默认 n','n',choice(('y','yes','n','no','strict','explore')))
        unknown=quality in ('y','yes','explore')
        lookback=ask('首次/重叠回看分钟数','120',integer(1,525600)) if interval!='day' else None
        if interval=='day':write('日线默认首次180天、后续7天重叠，并保留断连补取边界。')
        root=ask('已安装 Robinhood infra 根目录',str(Path.home()/'robinhood-trading-infra'),infra)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        default_db=f'local_data/{"-".join(names).lower()}-{interval}-{stamp}.sqlite3'
        database=ask('新日志文件（不会覆盖已有库）',default_db,db)
        argv=['poll-robinhood','--symbols',*names,'--interval',interval,'--bounds',bounds,'--poll-seconds',str(seconds),
              '--infra-root',root,'--db',database,'--output','tui']
        if count is not None:argv+=['--count',str(count)]
        if unknown:argv+=['--accept-unknown']
        if lookback is not None:argv+=['--lookback-minutes',str(lookback)]
        if mode=='close':argv+=['--align-close','--settle-seconds',str(settle)]
        write('\n请确认：'+', '.join(names)+' | '+interval+' | '+bounds+' | '+('UNKNOWN探索' if unknown else '严格质量'))
        write(('固定等待 '+str(seconds)+'秒' if mode=='fixed' else '收盘对齐 + '+str(settle)+'秒')+' | '+(str(count)+'轮' if count is not None else '无限运行，Ctrl-C停止'))
        write('命令预览：python -m pa_lens '+shlex.join(argv))
        write('原生EMA20/RSI14默认只读请求；不支持的周期/时段明确不可用，无本地回退。')
        if ask('开始？yes/no','no',choice(('yes','y','no','n'))) not in ('yes','y'):
            write('已取消，未启动采集。');return False
    except (Cancelled,KeyboardInterrupt):
        write('\n已取消，未启动采集。');return False
    write('启动只读终端监控；Ctrl-C停止。')
    try:runner(argv)
    except KeyboardInterrupt:write('\n监控已停止。')
    return True
