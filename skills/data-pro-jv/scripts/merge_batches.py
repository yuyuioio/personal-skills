"""Merge explicitly supplied, verified J-V extraction batches without plotting."""
import argparse,copy,hashlib,json,math
from pathlib import Path

KEYS=['Voc (V)','Jsc (mA/cm^2)','Fill Factor (%)','Efficiency (%)','Pmax (mW)','Imax (mA)','Vmax (V)','Rs (ohm)','Rsh (ohm)','Area (cm^2)','Isc (mA)']
def column(index):
    label='';index+=1
    while index:
        index,remainder=divmod(index-1,26);label=chr(65+remainder)+label
    return label
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs',type=Path,nargs='+')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ff-threshold',type=float,default=45)
    args=parser.parse_args()
    if not math.isfinite(args.ff_threshold):raise ValueError('FF threshold must be finite')
    batches=[];records=[];positions={};source_paths=[]
    for batch_path in dict.fromkeys(p.resolve() for p in args.inputs):
        data=json.loads(batch_path.read_text(encoding='utf-8-sig'))
        group=batch_path.stem
        if any(b['name']==group for b in batches):raise ValueError('Duplicate result-group labels; use unique batch JSON filenames')
        batches.append(dict(name=group,path=str(batch_path),uniqueCount=data['uniqueCount'],ffThreshold=data['ffThreshold'],ffCount=data['uniqueFFCount']))
        source_paths.extend(data['sourcePaths'])
        for original in data['records']:
            location=(original['path'],original['meta']['source_col'],original['meta']['group'])
            signature=[original['meta']['Name'],original['meta'].get('Time stamp'),[original['meta'][k] for k in KEYS],[[p[k] for k in ('v','i','j')] for p in original['points']],original.get('missingParameterValues',{})]
            fingerprint=hashlib.sha256(json.dumps(signature,separators=(',',':'),sort_keys=True).encode()).hexdigest()
            if location in positions:
                r=records[positions[location]]
                if r['fingerprint']!=fingerprint:raise ValueError('Conflicting extraction data at the same source location')
                if group not in r['resultGroups']:r['resultGroups'].append(group)
                continue
            r=copy.deepcopy(original)
            for key in ['plot','short','open','plotSign','scanDirection','sources','sourceLocation','duplicateOf','duplicateNote','recommendation','priority']:
                r.pop(key,None)
            r.update(id=len(records),fingerprint=fingerprint,resultGroups=[group])
            positions[location]=r['id'];records.append(r)
    seen={};unique=[]
    for r in records:
        r['duplicateOf']=seen.get(r['fingerprint'])
        if r['duplicateOf'] is None:seen[r['fingerprint']]=r['id'];unique.append(r)
    source_paths=list(dict.fromkeys(source_paths));folders=list(dict.fromkeys(str(Path(p).parent) for p in source_paths))
    matches={}
    for r in records:matches.setdefault(r['fingerprint'],[]).append(r)
    for r in unique:
        refs=matches[r['fingerprint']]
        r['sources']=[dict(file=s['file'],path=s['path'],groupKey=s['groupKey'],group=s['meta']['group'],parameterColumns=f"{column(s['meta']['source_col'])}:{column(s['meta']['source_col']+1)}",curveColumns=f"{column(s['meta']['source_col']+2)}:{column(s['meta']['source_col']+4)}") for s in refs]
        r['resultGroups']=list(dict.fromkeys(group for ref in refs for group in ref['resultGroups']))
        def source_text(s):
            label=s['file'] if len(folders)==1 else s['path']
            return f"{label}（组{s['group']}；参数{s['parameterColumns']}；扫描{s['curveColumns']}）"
        r['sourceLocation']=source_text(r['sources'][0])+''.join('\n重复来源：'+source_text(s) for s in r['sources'][1:])
        missing=r.get('missingParameterValues',{})
        if missing:r['sourceLocation']+='\n缺失参数（源文件为---）：'+', '.join(missing)
    def above(r,key,threshold):return isinstance(r['meta'][key],(float,int)) and math.isfinite(r['meta'][key]) and r['meta'][key]>threshold
    ff=[r for r in unique if above(r,'Fill Factor (%)',args.ff_threshold)]
    def best(key,candidates,minimum=False):
        values=[r['meta'][key] for r in candidates if isinstance(r['meta'][key],(float,int)) and math.isfinite(r['meta'][key])]
        return (min if minimum else max)(values,default=None)
    overall={key:best(key,unique,key=='Rs (ohm)') for key in ['Efficiency (%)','Fill Factor (%)','Voc (V)','Jsc (mA/cm^2)','Rs (ohm)','Rsh (ohm)']}
    cell_best={p:best('Efficiency (%)',[r for r in unique if any(s['groupKey']==p for s in r['sources'])]) for p in source_paths}
    tags=[('Efficiency (%)','汇总PCE最高'),('Fill Factor (%)','汇总FF最高'),('Voc (V)','Voc最高'),('Jsc (mA/cm^2)','Jsc最高'),('Rs (ohm)','Rs最低'),('Rsh (ohm)','Rsh最高')]
    for r in records:
        r['recommendation']='';r['priority']=0
        if r['duplicateOf'] is not None:continue
        reasons=[]
        for key,label in tags:
            if overall[key] is not None and r['meta'][key]==overall[key]:reasons.append(label)
        if cell_best[r['groupKey']] is not None and r['meta']['Efficiency (%)']==cell_best[r['groupKey']]:reasons.append('本电池PCE最高')
        other_best=[s['file'] for s in r['sources'][1:] if cell_best[s['groupKey']] is not None and r['meta']['Efficiency (%)']==cell_best[s['groupKey']]]
        if other_best:reasons.append('重复来源电池PCE最高：'+','.join(other_best))
        r['recommendation']='；'.join(reasons)
        r['priority']=3 if '汇总PCE最高' in reasons else 1 if reasons else 0
    out=dict(files=[Path(p).name for p in source_paths],sourcePaths=source_paths,sourceFolder='；'.join(folders),records=records,uniqueRecords=unique,rawCount=len(records),uniqueCount=len(unique),duplicateCount=len(records)-len(unique),ffCount=sum(above(r,'Fill Factor (%)',args.ff_threshold) for r in records),uniqueFFCount=len(ff),pceCount=0,uniquePCECount=0,ffThreshold=args.ff_threshold,pceThreshold=None,summary=True,resultBatches=batches,inputRetainedCount=sum(b['uniqueCount'] for b in batches))
    out['crossBatchDuplicateCount']=out['inputRetainedCount']-len(unique)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:out[k] for k in ['rawCount','inputRetainedCount','crossBatchDuplicateCount','uniqueCount','uniqueFFCount']},ensure_ascii=False))
if __name__=='__main__':main()
