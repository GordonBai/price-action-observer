"""Command line for local research; never sends orders."""
import argparse
import json
import os
from pathlib import Path
import sys
from .core import project_equal_leg


def main(argv=None):
    parser=argparse.ArgumentParser(description='Causal PA research tools; no order execution')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('wizard',help='interactive read-only monitor or daily swing setup; requires TTY')
    from .swing import add_arguments,run_swing
    add_arguments(sub.add_parser('swing',help='one-shot research scan of closed XNYS daily bars'))
    mm=sub.add_parser('mm',help='manual AB=CD projection (no automatic anchor selection)')
    for name in ('a','b','c'):mm.add_argument('--'+name,type=float,required=True)
    serve=sub.add_parser('serve',help='local authenticated ingestion and dashboard; needs PA_LENS_TOKEN')
    serve.add_argument('--enable-tradingview',action='store_true',help='explicitly enable query-secret ingress using separate PA_LENS_TV_TOKEN');serve.add_argument('--host',default='127.0.0.1');serve.add_argument('--port',type=int,default=8080);serve.add_argument('--db',default='local_data/lens.sqlite3')
    rep=sub.add_parser('replay',help='replay canonical JSONL/CSV bars; close timestamps required')
    rep.add_argument('--open-time-minutes',type=int,help='explicit adapter for bar-open timestamp field');rep.add_argument('input');rep.add_argument('--out',default='local_data/replay');rep.add_argument('--cost-bps',type=float,default=3)
    ev=sub.add_parser('evaluate',help='legacy hypothetical policy experiment, NOT observation accuracy; not the default evaluation')
    ev.add_argument('input');ev.add_argument('--open-time-minutes',type=int);ev.add_argument('--out',default='local_data/evaluation')
    poll=sub.add_parser('poll-alpaca',help='LEGACY explicit opt-in: poll completed 1-minute Alpaca bars; credentials/entitlement required')
    poll.add_argument('--symbol',default='SOXL');poll.add_argument('--feed',choices=['sip','iex'],default='sip')
    poll.add_argument('--db',default='local_data/alpaca-v02.sqlite3');poll.add_argument('--once',action='store_true')
    poll.add_argument('--poll-seconds',type=float,default=15);poll.add_argument('--lookback-minutes',type=int,default=120)
    poll.add_argument('--serve-port',type=int,help='optional same-process localhost panel using PA_LENS_TOKEN')
    for name in ('fetch-robinhood','poll-robinhood'):
        rh=sub.add_parser(name,help='primary read-only Robinhood MCP acquisition; no fallback')
        if name=='poll-robinhood':
            rh.add_argument('--output',choices=['tui','text','jsonl'],help='terminal format: TUI on request, text on a TTY, JSONL when piped')
        rh.add_argument('--symbols',nargs='+',default=['SOXL'])
        rh.add_argument('--start',required=name=='fetch-robinhood',help='RFC3339 range start; poll default uses lookback')
        rh.add_argument('--end',required=name=='fetch-robinhood',help='RFC3339 fixed end; poll default is now')
        rh.add_argument('--interval',choices=['minute','5minute','10minute','15minute','30minute','hour','4hour','day'],default='minute')
        rh.add_argument('--bounds',choices=['regular','extended','trading','24_5','24_7','hyper_trading'],default='regular')
        rh.add_argument('--adjustment',choices=['none','split','all'],default='split')
        rh.add_argument('--strict-interpolation',action='store_true',help='reject bars that omit the interpolated marker')
        rh.add_argument('--accept-unknown',action='store_true',help='deprecated no-op: omitted interpolated markers are accepted by default')
        rh.add_argument('--infra-root',help='existing installed Robinhood trading infra; never copies credentials')
        rh.add_argument('--codex-binary',default='codex');rh.add_argument('--timeout',type=float,default=30)
        rh.add_argument('--db',default='local_data/robinhood-v07.sqlite3')
        rh.add_argument('--capture-dir',help='optional private capture; inside project only local_data/')
        rh.add_argument('--no-native-context',action='store_true',help='disable automatic native context requests; no local fallback')
        rh.add_argument('--native-indicators',help='extra native types; interval context pack is automatic unless --no-native-context')
        rh.add_argument('--native-config',help='JSON list of type/parameters/interval/output objects')
        rh.add_argument('--native-output',default='latest',help='series, latest, or last:N')
        rh.add_argument('--native-interval',help='explicit provider interval, independent of PA period; required override for PA15m')
        rh.add_argument('--native-window-start',help='fixed RFC3339 warmup input start; defaults to first acquisition start')
        rh.add_argument('--quotes',action='store_true',help='separate raw quote evidence, never OHLC replacement')
        rh.add_argument('--align-close',action='store_true',help='wait for interval-close grid plus settle delay between polls')
        rh.add_argument('--settle-seconds',type=float,default=10)
        rh.add_argument('--once',action='store_true');rh.add_argument('--count',type=int,help='bounded poll iterations')
        rh.add_argument('--poll-seconds',type=float,default=30);rh.add_argument('--lookback-minutes',type=int,default=120)
        rh.add_argument('--serve-port',type=int,help='same-process authenticated localhost panel')
        rh.add_argument('--display-min-priority',type=int,choices=range(4),default=3)
        rh.add_argument('--display-cooldown-minutes',type=float,default=15)
    for command in (serve,poll):
        command.add_argument('--display-min-priority',type=int,choices=range(4),default=3)
        command.add_argument('--display-cooldown-minutes',type=float,default=15)
    args=parser.parse_args(argv)
    try:
        if args.command=='wizard':
            from .wizard import run_wizard
            run_wizard(main)
        elif args.command=='swing':
            return run_swing(args,parser)
        elif args.command in ('fetch-robinhood','poll-robinhood'):
            _run_robinhood(args,parser)
        elif args.command=='mm':print(json.dumps(project_equal_leg(args.a,args.b,args.c),ensure_ascii=False))
        elif args.command=='poll-alpaca':
            from .feed import AlpacaFeed,Poller,FeedError
            from .service import Journal,make_server
            import time,threading
            if not 5<=args.poll_seconds<=3600:parser.error('--poll-seconds must be 5..3600')
            feed=AlpacaFeed(os.environ.get('APCA_API_KEY_ID'),os.environ.get('APCA_API_SECRET_KEY'),args.feed)
            token=os.environ.get('PA_LENS_TOKEN','')
            if args.serve_port is not None and len(token)<16:parser.error('PA_LENS_TOKEN needs at least 16 characters for --serve-port')
            Path(args.db).parent.mkdir(parents=True,exist_ok=True)
            journal=Journal(args.db,display_config={'min_priority':args.display_min_priority,'cooldown_minutes':args.display_cooldown_minutes});poller=Poller(feed,journal,args.symbol,args.lookback_minutes);server=None
            if args.serve_port is not None:
                server=make_server(journal,token,port=args.serve_port)
                threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                while True:
                    try:print(json.dumps(poller.poll(),ensure_ascii=False),flush=True)
                    except (FeedError, ValueError) as ex:
                        print(json.dumps({'status':'FEED_ERROR','error':'Provider/ingestion validation failed; original journal preserved; inspect local audit and retry.','live_verified':False}),file=sys.stderr,flush=True)
                        if args.once:raise ValueError(str(ex))
                    if args.once:break
                    time.sleep(args.poll_seconds)
            except KeyboardInterrupt:pass
            finally:
                if server:server.shutdown();server.server_close()
                journal.close()
        elif args.command=='serve':
            token=os.environ.get('PA_LENS_TOKEN','')
            if len(token)<16:parser.error('PA_LENS_TOKEN must be set to a secret of at least 16 characters')
            from .service import Journal,make_server
            Path(args.db).parent.mkdir(parents=True,exist_ok=True)
            tv_token=os.environ.get('PA_LENS_TV_TOKEN') if args.enable_tradingview else None
            if args.enable_tradingview and (not tv_token or len(tv_token)<16 or tv_token==token):parser.error('PA_LENS_TV_TOKEN must be separate and at least 16 characters')
            journal=Journal(args.db,display_config={'min_priority':args.display_min_priority,'cooldown_minutes':args.display_cooldown_minutes});server=make_server(journal,token,host=args.host,port=args.port,tv_token=tv_token)
            print(f'Local research service: http://{args.host}:{args.port}; waiting for authenticated closed bars. NOT a verified live feed.',flush=True)
            try:server.serve_forever()
            except KeyboardInterrupt:pass
            finally:server.server_close();journal.close()
        else:
            from .replay import load_bars,run_replay,evaluate,evaluate_splits
            bars=list(load_bars(args.input,open_time_minutes=args.open_time_minutes))
            if args.command=='evaluate':
                result=evaluate_splits(bars);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
                (out/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                summary={k:{'bars':v['bars'],'scenarios':{c:r['summary'] for c,r in v['cost_scenarios'].items()}} for k,v in result['splits'].items()}
                (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({'output':str(out),'splits':list(result['splits'])}));return
            result=run_replay(bars)
            out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
            (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            (out/'events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in result['events']),encoding='utf-8')
            print(json.dumps({'output':str(out),'summary':result['summary']},ensure_ascii=False))
    except (ValueError,OSError) as ex:parser.error(str(ex))

def _run_robinhood(args,parser):
    from datetime import datetime,timedelta,timezone
    from .robinhood import open_robinhood,RobinhoodError,_time,_symbols,_options,INTERVAL_MINUTES
    from .rh_runtime import acquire,next_poll_delay,poll_start,poll_windows,source_identity
    from .service import Journal,make_server
    from .terminal_monitor import TerminalMonitor,TuiClock,terminal_output
    from .native_runtime import native_specs,validate_native,acquire_native,restore_native_start,context_specs
    import math,time,threading
    _symbols(args.symbols);_options('5minute' if args.interval=='15minute' else args.interval,args.bounds,args.adjustment)
    if args.interval=='15minute' and args.bounds!='regular':parser.error('derived 15minute requires regular bounds')
    next_poll_delay(datetime.now(timezone.utc),args.interval,args.settle_seconds)
    if not math.isfinite(args.poll_seconds) or not 5<=args.poll_seconds<=3600:parser.error('--poll-seconds must be 5..3600')
    if args.count is not None and not 1<=args.count<=10000:parser.error('--count must be 1..10000')
    if not 1<=args.lookback_minutes<=525600:parser.error('--lookback-minutes must be 1..525600')
    if not math.isfinite(args.timeout) or not 0<args.timeout<=300:parser.error('--timeout must be 0..300 seconds')
    if args.start:_time(args.start)
    if args.end:_time(args.end)
    if args.start and args.end and _time(args.start)>=_time(args.end):parser.error('start must precede end')
    configuration=None
    if args.native_config:
        config_path=Path(args.native_config)
        if config_path.stat().st_size>65536:parser.error('native config exceeds 64 KiB')
        configuration=json.loads(config_path.read_text(encoding='utf-8'))
    specs=native_specs(args.native_indicators,configuration,args.native_interval or args.interval,args.native_output)
    specs=context_specs(specs,interval=args.native_interval or args.interval,enabled=not args.no_native_context,bounds=args.bounds)
    native_start=_time(args.native_window_start) if args.native_window_start else (_time(args.start) if args.start else None)
    validation_end=_time(args.end) if args.end else datetime.now(timezone.utc)
    validation_start=native_start or validation_end-timedelta(days=180)
    validate_native(args.symbols,validation_start,validation_end,specs,args.bounds,args.adjustment)
    token=os.environ.get('PA_LENS_TOKEN','')
    if args.serve_port is not None and len(token)<16:parser.error('PA_LENS_TOKEN needs at least 16 characters for --serve-port')
    Path(args.db).parent.mkdir(parents=True,exist_ok=True)
    journal=Journal(args.db,display_config={'min_priority':args.display_min_priority,'cooldown_minutes':args.display_cooldown_minutes})
    server=None
    output=terminal_output(getattr(args,'output',None),sys.stdout) if args.command=='poll-robinhood' else 'jsonl'
    terminal=TerminalMonitor(args.symbols) if output in ('text','tui') else None
    source=source_identity(args.interval,args.bounds,args.adjustment,args.strict_interpolation)
    tui=TuiClock(sys.stdout,source=source,symbols=args.symbols,fixed_end=bool(args.end)) if output=='tui' else None
    try:
        if specs and native_start is None:
            saved_start=restore_native_start(journal,args.symbols,specs,args.bounds,args.adjustment)
            if saved_start:native_start=_time(saved_start)
        if args.serve_port is not None:
            server=make_server(journal,token,port=args.serve_port)
            threading.Thread(target=server.serve_forever,daemon=True).start()
        if tui:tui.start()
        # Context closes the owned app-server on errors or interruption; no auth UI.
        with open_robinhood(infra_root=args.infra_root,binary=args.codex_binary,timeout=args.timeout) as provider:
            iterations=0
            while True:
                now=datetime.now(timezone.utc)
                end=min(_time(args.end),now) if args.end else now
                if tui:tui.status('PULLING',pull_started=now)
                windows=poll_windows(journal,args.symbols,end,args.interval,args.lookback_minutes,source,
                                     explicit_start=_time(args.start) if args.start else None)
                receipts=[]
                try:
                    for symbols,start in windows:
                        result=acquire(provider,journal,symbols,start,end,interval=args.interval,bounds=args.bounds,
                            adjustment_type=args.adjustment,strict_interpolation=args.strict_interpolation,capture_dir=args.capture_dir,include_quotes=args.quotes)
                        if specs:result['provider_indicators']='SEPARATE_NATIVE_REQUESTS_FOLLOW'
                        if terminal:receipts.append((symbols,result))
                        else:print(json.dumps(result,ensure_ascii=False),flush=True)
                except (RobinhoodError,ValueError):
                    # Fail visibly, not indefinite silent retries or alternate providers.
                    raise ValueError('Robinhood acquisition/validation failed; inspect local health/audit. No fallback was used.') from None
                if specs:
                    if native_start is None:
                        timeframe='15' if args.interval=='15minute' else ('D' if args.interval=='day' else str(INTERVAL_MINUTES[args.interval]))
                        coverage=[journal.coverage_start(symbol,timeframe,source) for symbol in args.symbols]
                        native_start=min([_time(t) for t in coverage if t]+[start for _,start in windows])
                    native=acquire_native(provider,journal,args.symbols,native_start,end,specs,bounds=args.bounds,
                        adjustment_type=args.adjustment,capture_dir=args.capture_dir)
                    if not terminal:print(json.dumps({'native_indicators':native,'pa_interval':args.interval,'native_input_window_start':native_start.isoformat(),
                        'notice':'Native values inform current indicator context only; pure candle patterns and historical events are unchanged. Warmup/source quality unknown; not calibrated signals.'},ensure_ascii=False),flush=True)
                displayed_at=datetime.now(timezone.utc)
                current=journal.snapshot(now=displayed_at)
                if terminal:
                    view=terminal.view(current,receipts,now=displayed_at,source=source,
                                       fixed_end=bool(args.end),native_enabled=bool(specs))
                    if tui:tui.publish(view)
                    else:print(view['text'],flush=True)
                else:print(json.dumps({'native_pa_context':[{'symbol':s['symbol'],'timeframe':s['timeframe'],**s['native_interpretation']} for s in current['streams'] if s['symbol'] in args.symbols and s['source']==source]},ensure_ascii=False),flush=True)
                iterations+=1
                if args.command=='fetch-robinhood' or args.once or (args.count and iterations>=args.count):
                    if tui:tui.status('DONE')
                    break
                delay=next_poll_delay(datetime.now(timezone.utc),args.interval,args.settle_seconds) if args.align_close else args.poll_seconds
                time.sleep(delay)
    except RobinhoodError as exc:
        if tui:tui.status('ERROR')
        raise ValueError(str(exc)) from None
    except (ValueError,OSError):
        if tui:tui.status('ERROR')
        raise
    except KeyboardInterrupt:
        if tui:tui.status('STOPPED')
    finally:
        if tui:
            tui.close()
            print(flush=True)
        if server:server.shutdown();server.server_close()
        journal.close()

if __name__=='__main__':main()
