import json,sys,glob,os
from datetime import datetime
# цены $/Мтокенов (input, cache_write, cache_read, output) — относительные, по прайсу Anthropic
P={'opus':(5,6.25,0.5,25),'sonnet':(3,3.75,0.3,15),'haiku':(1,1.25,0.1,5)}
def fam(m):
    for k in P:
        if k in (m or ''): return k
    return 'opus'
def stats(path):
    inp=cw=cr=out=0; tools=0; model=None; ts=[]; seen=set()
    for line in open(path,encoding='utf8'):
        try:d=json.loads(line)
        except:continue
        t=d.get('timestamp')
        if t: ts.append(datetime.fromisoformat(t.replace('Z','+00:00')))
        m=d.get('message') or {}
        if d.get('type')=='assistant' and isinstance(m,dict):
            mid=m.get('id')
            model=m.get('model') or model
            for c in m.get('content') or []:
                if isinstance(c,dict) and c.get('type')=='tool_use': tools+=1
            if mid in seen: continue
            seen.add(mid)
            u=m.get('usage') or {}
            inp+=u.get('input_tokens',0); cw+=u.get('cache_creation_input_tokens',0)
            cr+=u.get('cache_read_input_tokens',0); out+=u.get('output_tokens',0)
    p=P[fam(model)]
    cost=(inp*p[0]+cw*p[1]+cr*p[2]+out*p[3])/1e6
    dur=(max(ts)-min(ts)).total_seconds() if ts else 0
    return dict(model=fam(model),turns=len(seen),tools=tools,inp=inp,cw=cw,cr=cr,out=out,cost=cost,dur=dur,start=min(ts) if ts else None)
if __name__=='__main__':
    d=sys.argv[1]
    rows=[]
    for f in sorted(glob.glob(os.path.join(d,'agent-*.jsonl'))):
        meta={}
        mf=f.replace('.jsonl','.meta.json')
        if os.path.exists(mf):
            try: meta=json.load(open(mf,encoding='utf8'))
            except: pass
        s=stats(f); s['desc']=(meta.get('description') or meta.get('agentType') or os.path.basename(f))[:38]
        rows.append(s)
    rows.sort(key=lambda r:r['start'] or datetime.min)
    print(f"{'desc':38} {'mdl':6} {'turn':>4} {'tool':>4} {'new_in':>7} {'c_wr':>7} {'c_rd':>9} {'out':>6} {'$':>6} {'sec':>5}")
    for r in rows:
        print(f"{r['desc']:38} {r['model']:6} {r['turns']:4} {r['tools']:4} {r['inp']:7} {r['cw']:7} {r['cr']:9} {r['out']:6} {r['cost']:6.3f} {r['dur']:5.0f}")
