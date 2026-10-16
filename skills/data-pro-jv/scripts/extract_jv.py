import csv, json, math, hashlib, argparse
from pathlib import Path

parser=argparse.ArgumentParser(description='Extract only explicitly supplied photovoltaic J-V CSV files.')
parser.add_argument('inputs',nargs='+',type=Path)
parser.add_argument('--output',required=True,type=Path)
parser.add_argument('--ff-threshold',type=float,default=45)
parser.add_argument('--pce-threshold',type=float,default=8.5)
args=parser.parse_args()
paths=list(dict.fromkeys(p.resolve() for p in args.inputs))
files=[p.name for p in paths]
keys=['Voc (V)','Jsc (mA/cm^2)','Fill Factor (%)','Efficiency (%)','Pmax (mW)','Imax (mA)','Vmax (V)','Rs (ohm)','Rsh (ohm)','Area (cm^2)','Isc (mA)']
records=[]
for source in paths:
    filename=source.name
    try: text=source.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError: text=source.read_text(encoding='gb18030')
    rows=list(csv.reader(text.splitlines()))
    end=next(i for i,r in enumerate(rows) if r and r[0].startswith('==='))
    starts=[i for i,x in enumerate(rows[1]) if x=='[Information]' and rows[1][i+2:i+5]==['[Volt (V)]','[Current (mA)]','[J (mA/cm^2)]']]
    if not starts: raise ValueError(f'{source}: unrecognized J-V group headers')
    summary_header=rows[end+1]
    summary=[dict(zip(summary_header,r)) for r in rows[end+2:] if len(r)>1 and r[1]]
    assert len(summary)==len(starts)
    for idx,start in enumerate(starts):
        m={}; points=[]
        for row_no,r in enumerate(rows[2:end],3):
            if len(r)<=start+4: continue
            if r[start]: m[r[start]]=r[start+1]
            try:
                v,i,j=map(float,r[start+2:start+5])
                if all(math.isfinite(x) for x in (v,i,j)):
                    points.append(dict(v=v,i=i,j=j,row=row_no))
            except ValueError: pass
        for k in keys:
            if k not in m or not m[k].strip(): raise ValueError(f'{source}, group {idx+1}: missing parameter {k}; review without replacing it with zero')
            m[k]=float(m[k])
            if not math.isfinite(m[k]): raise ValueError(f'{source}, group {idx+1}: non-finite parameter {k}; review without inventing a numeric value')
        for k in keys: assert math.isclose(m[k],float(summary[idx][k]),abs_tol=1e-12),(filename,idx,k)
        assert m['Name']==summary[idx]['Name']
        m.update(group=int(rows[0][start+1]),source_col=start)
        label=f'{source.stem} / {m["Name"]}'
        r=dict(id=len(records),file=filename,path=str(source),groupKey=str(source),cell=source.stem,label=label,meta=m,points=points)
        # A name alone is never used to identify duplicates. Compare all 11 metrics,
        # complete V/I/J sweeps, test-point identity, area and original timestamp.
        sig=[m['Name'],m.get('Time stamp'),[m[k] for k in keys],[[p[x] for x in ('v','i','j')] for p in points]]
        r['fingerprint']=hashlib.sha256(json.dumps(sig,separators=(',',':')).encode()).hexdigest()
        records.append(r)

seen={}
for r in records:
    r['duplicateOf']=seen.get(r['fingerprint'])
    if r['duplicateOf'] is None: seen[r['fingerprint']]=r['id']
unique=[r for r in records if r['duplicateOf'] is None]
def excel_col(index):
    s=''; index+=1
    while index:
        index,remainder=divmod(index-1,26);s=chr(65+remainder)+s
    return s
for r in unique:
    sources=[s for s in records if s['fingerprint']==r['fingerprint']]
    r['sources']=[dict(file=s['file'],path=s['path'],groupKey=s['groupKey'],group=s['meta']['group'],parameterColumns=f"{excel_col(s['meta']['source_col'])}:{excel_col(s['meta']['source_col']+1)}",curveColumns=f"{excel_col(s['meta']['source_col']+2)}:{excel_col(s['meta']['source_col']+4)}") for s in sources]
    def source_text(s):
        file_label=s['file'] if len({p.parent for p in paths})==1 else s['path']
        return f"{file_label}（组{s['group']}；参数{s['parameterColumns']}；扫描{s['curveColumns']}）"
    r['sourceLocation']=source_text(r['sources'][0])+''.join('\n重复来源：'+source_text(s) for s in r['sources'][1:])
ff=[r for r in unique if r['meta']['Fill Factor (%)']>args.ff_threshold]
best_global=max((r['meta']['Efficiency (%)'] for r in unique),default=None)
best_cells={str(p):max((r['meta']['Efficiency (%)'] for r in unique if any(s['groupKey']==str(p) for s in r['sources'])),default=None) for p in paths}
ff_best=max((r['meta']['Fill Factor (%)'] for r in unique),default=None)
metric_best={k:max((r['meta'][k] for r in unique),default=None) for k in ['Voc (V)','Jsc (mA/cm^2)','Rsh (ohm)']}
rs_best=min((r['meta']['Rs (ohm)'] for r in unique),default=None)
for r in records:
    tags=[]; m=r['meta']
    if r['duplicateOf'] is not None:
        r['duplicateNote']='与'+records[r['duplicateOf']]['label']+'完全重复'
        r['recommendation']='重复引用（不重复推荐）'
        r['priority']=0
    else:
        r['duplicateNote']='未发现完全重复'
        if m['Efficiency (%)']==best_global: tags.append('本批PCE最高')
        if m['Efficiency (%)']==best_cells[r['groupKey']]: tags.append('本电池PCE最高')
        other_best=[s['file'] for s in r['sources'][1:] if m['Efficiency (%)']==best_cells[s['groupKey']]]
        if other_best: tags.append('重复来源电池PCE最高：'+','.join(other_best))
        if m['Fill Factor (%)']==ff_best: tags.append('本批FF最高')
        for k,label in [('Voc (V)','Voc最高'),('Jsc (mA/cm^2)','Jsc最高'),('Rsh (ohm)','Rsh最高')]:
            if m[k]==metric_best[k]: tags.append(label)
        if m['Rs (ohm)']==rs_best: tags.append('Rs最低')
        r['recommendation']='；'.join(tags) if tags else ''
        r['priority']=3 if m['Efficiency (%)']==best_global else 1 if tags else 0

out=dict(files=files,sourcePaths=[str(p) for p in paths],sourceFolder='；'.join(dict.fromkeys(str(p.parent) for p in paths)),records=records,uniqueRecords=unique,rawCount=len(records),uniqueCount=len(unique),duplicateCount=len(records)-len(unique),ffCount=sum(r['meta']['Fill Factor (%)']>args.ff_threshold for r in records),uniqueFFCount=len(ff),pceCount=sum(r['meta']['Efficiency (%)']>args.pce_threshold for r in records),uniquePCECount=sum(r['meta']['Efficiency (%)']>args.pce_threshold for r in unique),jvCurvesGenerated=0,ffThreshold=args.ff_threshold,pceThreshold=args.pce_threshold)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in out.items() if k not in ['records','uniqueRecords']},ensure_ascii=False))
