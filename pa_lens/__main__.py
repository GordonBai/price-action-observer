"""Command line for local research; never sends orders."""
import argparse
import json
import os
from pathlib import Path
import sys
from .core import project_equal_leg


def main():
    parser=argparse.ArgumentParser(description='Causal PA research tools; no order execution')
    sub=parser.add_subparsers(dest='command',required=True)
    mm=sub.add_parser('mm',help='manual AB=CD projection (no automatic anchor selection)')
    for name in ('a','b','c'):mm.add_argument('--'+name,type=float,required=True)
    serve=sub.add_parser('serve',help='local authenticated ingestion and dashboard; needs PA_LENS_TOKEN')
    serve.add_argument('--enable-tradingview',action='store_true',help='explicitly enable query-secret ingress using separate PA_LENS_TV_TOKEN');serve.add_argument('--host',default='127.0.0.1');serve.add_argument('--port',type=int,default=8080);serve.add_argument('--db',default='local_data/lens.sqlite3')
    rep=sub.add_parser('replay',help='replay canonical JSONL/CSV bars; close timestamps required')
    rep.add_argument('--open-time-minutes',type=int,help='explicit adapter for bar-open timestamp field');rep.add_argument('input');rep.add_argument('--out',default='local_data/replay');rep.add_argument('--cost-bps',type=float,default=3)
    ev=sub.add_parser('evaluate',help='legacy hypothetical policy experiment, NOT observation accuracy; not the default evaluation')
    ev.add_argument('input');ev.add_argument('--open-time-minutes',type=int);ev.add_argument('--out',default='local_data/evaluation')
    poll=sub.add_parser('poll-alpaca',help='poll completed 1-minute Alpaca bars; credentials/entitlement required')
    poll.add_argument('--symbol',default='SOXL');poll.add_argument('--feed',choices=['sip','iex'],default='sip')
    poll.add_argument('--db',default='local_data/alpaca-v02.sqlite3');poll.add_argument('--once',action='store_true')
    poll.add_argument('--poll-seconds',type=float,default=15);poll.add_argument('--lookback-minutes',type=int,default=120)
    poll.add_argument('--serve-port',type=int,help='optional same-process localhost panel using PA_LENS_TOKEN')
    for command in (serve,poll):
        command.add_argument('--display-min-priority',type=int,choices=range(4),default=3)
        command.add_argument('--display-cooldown-minutes',type=float,default=15)
    args=parser.parse_args()
    try:
        if args.command=='mm':print(json.dumps(project_equal_leg(args.a,args.b,args.c),ensure_ascii=False))
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
                    except FeedError as ex:
                        print(json.dumps({'status':'FEED_ERROR','error':str(ex),'live_verified':False}),file=sys.stderr,flush=True)
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

if __name__=='__main__':main()
