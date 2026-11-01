import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { Workbook, SpreadsheetFile, FileBlob } from '@oai/artifact-tool';

const options={},argv=process.argv.slice(2);
for(let i=0;i<argv.length;i+=2){
 if(!['--data','--output','--preview-dir','--python','--mode'].includes(argv[i])||!argv[i+1])throw new Error('Usage: --data input.json --output result.xlsx [--python executable] [--preview-dir previews] [--mode full|parameters]');
 options[argv[i]]=argv[i+1];
}
if(!options['--data']||!options['--output'])throw new Error('--data and --output required');
if(options['--mode']&&!['full','parameters'].includes(options['--mode']))throw new Error('Invalid mode');
const here=path.dirname(fileURLToPath(import.meta.url)),python=options['--python']||'python';
function run(script,args){const p=spawnSync(python,[path.join(here,script),...args],{encoding:'utf8',windowsHide:true});if(p.error||p.status!==0)throw new Error(`${script}: ${p.error?.message||p.stderr||p.stdout}`);console.log(p.stdout.trim());}
const input=path.resolve(options['--data']),output=path.resolve(options['--output']);
await fs.mkdir(path.dirname(output),{recursive:true});
run('select_metrics.py',['--data',input,'--output',`${output}.metrics.json`]);
const data=JSON.parse(await fs.readFile(input,'utf8')),selection=JSON.parse(await fs.readFile(`${output}.metrics.json`,'utf8'));
const records=data.uniqueRecords.map(r=>({...r,...selection.repeatedTests.annotations[String(r.id)]})),byId=new Map(records.map(r=>[r.id,r])),inputIndex=new Map(records.map((r,i)=>[r.id,i]));
const wb=Workbook.create(),ink='#183153',blue='#2563EB';
const overview=wb.worksheets.add('总结');
const keys=['Jsc (mA/cm^2)','Voc (V)','Fill Factor (%)','Efficiency (%)','Pmax (mW)','Imax (mA)','Vmax (V)','Rs (ohm)','Rsh (ohm)','Isc (mA)','Area (cm^2)'];
const labels=['Jsc (mA/cm²)','Voc (V)','FF (%)','PCE (%)','Pmax (mW)','Imax (mA)','Vmax (V)','Rs (Ω)','Rsh (Ω)','Isc (mA)','面积 (cm²)'];
const fields=[['编号',r=>r.label],...keys.slice(0,10).map((k,i)=>[labels[i],r=>r.meta[k]??null,k]),['日期',r=>r.meta['Time stamp']??null],
 ['面积 (cm²)',r=>r.meta['Area (cm^2)']??null,'Area (cm^2)'],['记录ID',r=>r.id],['原始组号',r=>r.meta.group??null],['样品编号',r=>r.sampleId??r.cell??null],['测量组/次数',r=>r.measurementGroup??r.file??null],
 ['测试点',r=>r.pointId??null],['保留状态',r=>r.retentionStatus??null],['择优依据',r=>r.repeatReason??null],['比较提示',r=>r.repeatWarning||null],['异常标记',r=>r.anomalyFlag??null],['异常依据',r=>r.anomalyReason??null],['所属结果组',r=>(r.resultGroups||[]).join('\n')],
 ['优选关注',r=>r.recommendation||null],['文件名称 / 位置（含重复来源）',r=>r.sourceLocation||null]];
function col(n){let s='';for(;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;}
function base(s,range){s.showGridLines=false;s.getRange(range).format={font:{name:'Arial',size:10,color:ink},rowHeight:20,horizontalAlignment:'center',verticalAlignment:'center'};}
function box(s,range){s.getRange(range).format.borders={preset:'all',style:'thin',color:'#94A3B8'};}
function header(s,range){s.getRange(range).format={fill:ink,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:30};box(s,range);}
function line(s,row,text){s.getRange(`A${row}:J${row}`).merge();s.getRange(`A${row}`).values=[[text]];s.getRange(`A${row}:J${row}`).format.wrapText=true;s.getRange(`A${row}:J${row}`).format.rowHeight=Math.max(24,Math.ceil([...text].length/70)*17);}
function width(s){s.getRange('A:A').format.columnWidth=26;s.getRange('B:J').format.columnWidth=12;}
function lines(value,width){return typeof value==='string'?value.split('\n').reduce((n,t)=>n+Math.max(1,Math.ceil([...t].length/(width/1.6))),0):1;}
function table(s,start,items,{extras=[],role='parameters',average=false}={}){
 const defs=[...fields.slice(0,-1),...extras,fields.at(-1)],positions=[],separators=[];let cursor=start+1,lastGroup=null;
 for(const r of items){
  const group=r.sampleId??r.groupKey??r.cell;
  if(lastGroup!==null&&group!==lastGroup){separators.push(cursor);cursor++;}
  positions.push({id:r.id,row:cursor});lastGroup=group;cursor++;
 }
 const end=defs.length,dataBottom=Math.max(start+1,cursor-1),averageRow=average?dataBottom+1:null,bottom=averageRow??dataBottom,averageFormulas={};
 if(end>16384||bottom>1048576)throw new Error('Table exceeds Excel dimensions; split scope');
 base(s,`A${start}:${col(end)}${bottom}`);
 s.getRange(`A${start}:${col(end)}${start}`).values=[defs.map(d=>d[0])];header(s,`A${start}:${col(end)}${start}`);
 const columnWidth=label=>label.startsWith('文件名称')?48:['择优依据','比较提示','未入选原因','异常依据'].includes(label)?42:label==='优选关注'?32:label==='日期'?22:12;
 defs.forEach(([label],i)=>s.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=i===0?29:columnWidth(label));
 function ref(p,i){return `${col(i+1)}${p.row}`;}
 for(const [idx,p] of positions.entries()){
  const r=byId.get(p.id),values=defs.map(([,get])=>get(r,inputIndex.get(r.id)));
  const range=`A${p.row}:${col(end)}${p.row}`;
  s.getRange(range).values=[values];s.getRange(range).format.fill=idx%2?'#E8F0FA':'#FFFFFF';s.getRange(range).format.wrapText=true;box(s,range);
  defs.forEach(([label],i)=>{
   const v=values[i],cell=s.getRange(ref(p,i));
   if(typeof v==='number')cell.setNumberFormat(label.includes('(%)')?'0.00000"%"':label==='记录ID'||label==='原始组号'||label==='原始测量序号'?'0':label==='Rs (Ω)'||label==='Rsh (Ω)'?'0.00':'0.00000');
   if(label==='优选关注'&&v)cell.format.font.color='#166534';
   if(label==='异常标记'&&v)cell.format.fill='#FEE2E2';
   if(label.startsWith('文件名称')&&(r.sources||[]).length>1)cell.format.font.color='#7C3AED';
  });
  s.getRange(range).format.rowHeight=Math.min(409,Math.max(22,...values.map((v,i)=>4+13*lines(v,i===0?29:columnWidth(defs[i][0])))));
 }
 for(const gap of separators){const r=`A${gap}:${col(end)}${gap}`;s.getRange(r).format.fill=ink;s.getRange(r).format.rowHeight=8;}
 if(!items.length)s.getRange(`A${start+1}`).values=[['无记录']];
 if(average){
  const range=`A${averageRow}:${col(end)}${averageRow}`;s.getRange(range).format={fill:'#DCECE4',font:{name:'Arial',size:10,bold:true,color:ink},rowHeight:25};box(s,range);
  s.getRange(`A${averageRow}`).values=[['平均值（本表入选记录）']];
  defs.forEach(([label,,key],i)=>{
   if(!key)return;
   const letter=col(i+1),refs=`${letter}${start+1}:${letter}${dataBottom}`,ref=`${letter}${averageRow}`;
   averageFormulas[ref]=`=IF(COUNT(${refs})=0,"无法计算",AVERAGE(${refs}))`;
   s.getRange(ref).formulas=[[averageFormulas[ref]]];s.getRange(ref).setNumberFormat(label.includes('(%)')?'0.00000"%"':'0.00000');
  });
 }
 s.freezePanes.freezeColumns(1);
 return {sheet:s.name,start,bottom,dataBottom,averageRow,averageFormulas,end,orientation:'rows',role,positions,labels:defs.map(d=>d[0]),metricFields:defs.flatMap((d,i)=>d[2]?[{key:d[2],index:i}]:[]),sourceIndex:defs.length-1};
}
function tableRef(table,p,index){return `${col(index+1)}${p.row}`;}
const chartManifest=[],tableManifest=[],rawManifest=[],statisticsManifest=[],views=[];
for(const [name,result] of Object.entries(selection.metrics)){
 const scopeRecords=records.filter(r=>result.scopeIds.includes(r.id));
 const s=wb.worksheets.add(`${name}筛选`);base(s,'A1:J26');width(s);s.tabColor=ink;
 line(s,2,`${name} 入选数据分布`);s.getRange('A2').format.font={name:'Arial',size:14,bold:true,color:ink};
 s.getRange('A4').values=[[`最终均值 (${result.unit})`]];s.getRange('B4:C4').merge();
 s.getRange('D4:G4').merge();s.getRange('D4').values=[['相对均方根偏差（用户所称MSE）']];s.getRange('H4:J4').merge();
 s.getRange('A4:J4').format.rowHeight=35;s.getRange('B4:C4').format.font={name:'Arial',size:14,bold:true,color:blue};s.getRange('H4:J4').format.font={name:'Arial',size:14,bold:true,color:blue};
 s.getRange('B4').setNumberFormat(result.unit==='%'?'0.00000"%"':'0.00000');s.getRange('H4').setNumberFormat('0.00000000%');
 s.getRange('A5').values=[[`原始MSE (${result.unit==='%'?'百分点²':`(${result.unit})²`})`]];s.getRange('B5:C5').merge();s.getRange('D5:G5').merge();s.getRange('D5').values=[[`总体标准差 σ (${result.unit==='%'?'百分点':result.unit})`]];s.getRange('H5:J5').merge();s.getRange('B5').setNumberFormat('0.00000000');s.getRange('H5').setNumberFormat('0.00000000');s.getRange('A5:J5').format.rowHeight=25;
 const sigma=result.mse===null?null:Math.sqrt(result.mse);
 line(s,6,`${result.conditionLabel}。入选 ${result.count} / 有效 ${result.validCount} / 候选 ${result.candidateCount}。${result.status}。范围：${result.sourceFiles.join('、')}`);
 line(s,7,`相对均方根偏差 = √[Σ(x−均值)²/n] ÷ |均值|，≤ ${result.threshold*100}%。${result.maxAbsoluteGapAllowed===null?'':`PCE距候选最大值≤${result.maxAbsoluteGapAllowed}个百分点。`}修改后公式重算；重新筛选需重新运行。`);
 s.getRange('K4:L4').values=[['相对偏差上限',result.threshold]];s.getRange('L4').setNumberFormat('0.0%');
 s.getRange('K5:L5').values=[['最大绝对差上限（百分点）',result.maxAbsoluteGapAllowed]];
 const spreadNote=result.count>=2?'橙线：均值±1σ（标准差见H5，分母为n）。':'入选少于2点，不显示标准差标记。';
 line(s,8,`蓝点：入选原始值；绿线：均值；${spreadNote}横向位置仅用于错开重叠点。`);
 if(!result.passed||result.count<2)s.getRange('A6:J6').format.fill='#FEF3C7';
 const ids=new Set(result.selectedIds),selected=scopeRecords.filter(r=>ids.has(r.id));
 const deviationLabel=`与均值之差 (${result.unit})`,squareLabel=`偏差平方 ((${result.unit})²)`,gapLabel='距候选最大PCE (百分点)';
 const extraFields=[['原始测量序号',(_,i)=>i+1],[deviationLabel,()=>null],[squareLabel,()=>null],...(result.maxAbsoluteGapAllowed===null?[]:[[gapLabel,()=>null]])];
 const t=table(s,28,selected,{extras:extraFields,role:'selected',average:true});tableManifest.push(t);
 const metricIndex=t.metricFields.find(f=>f.key===result.key).index,deviationIndex=t.labels.indexOf(deviationLabel),squareIndex=t.labels.indexOf(squareLabel),gapIndex=t.labels.indexOf(gapLabel);
 const first=t.positions[0]?.row??29,last=t.positions.at(-1)?.row??29,selectedRange=`$${col(metricIndex+1)}$${first}:$${col(metricIndex+1)}$${last}`,squareRange=`$${col(squareIndex+1)}$${first}:$${col(squareIndex+1)}$${last}`;
 const formulas={B4:`=IF(COUNT(${selectedRange})=0,"无法计算",AVERAGE(${selectedRange}))`,B5:`=IF(COUNT(${selectedRange})=0,"无法计算",SUM(${squareRange})/COUNT(${selectedRange}))`,H5:`=IF(COUNT(${selectedRange})=0,"无法计算",SQRT(B5))`,H4:`=IF(COUNT(${selectedRange})=0,"无法计算",IF(B4=0,"无法计算",H5/ABS(B4)))`};
 const literal=text=>`"${String(text).replaceAll('"','""')}"`;
 const gapRange=gapIndex<0?null:`$${col(gapIndex+1)}$${first}:$${col(gapIndex+1)}$${last}`;
 const passFormula=gapRange?`AND(H4<=$L$4,MAX(${gapRange})<=$L$5)`:'H4<=$L$4';
 formulas.A6=`=${literal(`${result.conditionLabel}。当前参与计算 `)}&COUNT(${selectedRange})&${literal(` / 本次候选 ${result.candidateCount}。`)}&IF(COUNT(${selectedRange})=0,"无有效值，无法计算",IF(B4=0,"均值为0，相对偏差无法计算",IF(COUNT(${selectedRange})=1,"仅1点，无法评价离散性",IF(${passFormula},"符合本指标筛选上限","超出本指标上限，需重新筛选"))))&${literal(`。范围：${result.sourceFiles.join('、')}`)}`;
 for(const [ref,formula] of Object.entries(formulas))s.getRange(ref).formulas=[[formula]];
 for(const p of t.positions){
  const ref=tableRef(t,p,metricIndex),dev=tableRef(t,p,deviationIndex),sq=tableRef(t,p,squareIndex);
  formulas[dev]=`=${ref}-$B$4`;formulas[sq]=`=${dev}^2`;
  for(const cell of [dev,sq]){s.getRange(cell).formulas=[[formulas[cell]]];s.getRange(cell).setNumberFormat('0.00000000');}
  if(gapIndex>=0){const gap=tableRef(t,p,gapIndex);formulas[gap]=`=ABS($N$4-${ref})`;s.getRange(gap).formulas=[[formulas[gap]]];s.getRange(gap).setNumberFormat('0.00000000');}
 }
 Object.assign(formulas,t.averageFormulas);
 const statistics={sheet:s.name,selectedRange,squareRange,metricIndex,deviationIndex,squareIndex,gapIndex,formulas};statisticsManifest.push(statistics);
 for(const p of t.positions)if(result.bestIds.includes(p.id))s.getRange(tableRef(t,p,metricIndex)).format.fill='#FEF3C7';
 const excludedStart=t.bottom+3;line(s,excludedStart,'未入选原始数据（完整记录仍保留于全部参数）');
 const excluded=table(s,excludedStart+1,scopeRecords.filter(r=>!ids.has(r.id)),{extras:[['未入选原因',r=>result.excludedReasons[String(r.id)]]],role:'excluded'});tableManifest.push(excluded);
 if(gapIndex>=0){
  const retainedSet=new Set(selection.repeatedTests.selectedIds),refs=[];
  for(const source of [t,excluded])for(const p of source.positions)if(retainedSet.has(p.id)&&Number.isFinite(byId.get(p.id).meta[result.key]))refs.push(tableRef(source,p,source.metricFields.find(f=>f.key===result.key).index));
  s.getRange('M4').values=[['候选最大PCE (%)']];
  formulas.N4=refs.length?`=IF(COUNT(${refs.join(',')})=0,"无法计算",MAX(${refs.join(',')}))`:'="无法计算"';s.getRange('N4').formulas=[[formulas.N4]];s.getRange('N4').setNumberFormat('0.00000"%"');
 }
 const helper=excluded.bottom+4;
 if(selected.length){
  const rawRefs=t.positions.map(p=>tableRef(t,p,metricIndex));
  s.getRange(`A${helper}:B${helper}`).values=[['分布横向位置（无物理含义）',`${name} 入选原始值`]];
  const xs=selected.map((_,i)=>1+(((i*.618033988749895)%1)-.5)*.24);
  s.getRange(`A${helper+1}:A${helper+selected.length}`).values=xs.map(x=>[x]);
  s.getRange(`B${helper+1}:B${helper+selected.length}`).formulas=rawRefs.map(ref=>[`=${ref}`]);
  const entries=[{name:'入选原始值',kind:'points',ids:selected.map(r=>r.id),x:xs,y:selected.map(r=>r.meta[result.key]),xFormula:`'${s.name}'!$A$${helper+1}:$A$${helper+selected.length}`,yFormula:`'${s.name}'!$B$${helper+1}:$B$${helper+selected.length}`}];
  s.getRange(`D${helper}:E${helper+2}`).values=[['均值横向位置','均值'],[.8,null],[1.2,null]];
  for(const row of [helper+1,helper+2]){formulas[`E${row}`]='=$B$4';s.getRange(`E${row}`).formulas=[['=$B$4']];}
  entries.push({name:'均值',kind:'mean',x:[.8,1.2],y:[result.mean,result.mean],xFormula:`'${s.name}'!$D$${helper+1}:$D$${helper+2}`,yFormula:`'${s.name}'!$E$${helper+1}:$E$${helper+2}`});
  if(selected.length>=2){
   s.getRange(`G${helper}:H${helper+2}`).values=[['标准差标记位置','均值±1σ'],[1.28,null],[1.28,null]];
   formulas[`H${helper+1}`]='=$B$4-$H$5';formulas[`H${helper+2}`]='=$B$4+$H$5';s.getRange(`H${helper+1}:H${helper+2}`).formulas=[['=$B$4-$H$5'],['=$B$4+$H$5']];
   entries.push({name:'均值±1σ（总体）',kind:'sd',x:[1.28,1.28],y:[result.mean-sigma,result.mean+sigma],xFormula:`'${s.name}'!$G$${helper+1}:$G$${helper+2}`,yFormula:`'${s.name}'!$H$${helper+1}:$H$${helper+2}`});
  }
  // Seed documented contiguous chart construction, then bind real per-series ranges.
  const seedCols=entries.length+1,seedEnd=col(12+entries.length);
  s.getRange(`L10:${seedEnd}12`).values=[['X',...entries.map(e=>e.name)],[1,...entries.map(e=>e.y[0])],[1.1,...entries.map(e=>e.y.at(-1))]];
  const chart=s.charts.add('scatter',s.getRange(`L10:${seedEnd}12`));
  entries.forEach((e,i)=>{chart.series.items[i].categoryFormula=e.xFormula;chart.series.items[i].formula=e.yFormula;chart.series.items[i].name=e.name;});
  s.getRange(`L10:${seedEnd}12`).values=Array.from({length:3},()=>Array(seedCols).fill(null));
  chart.title=selected.length>=2?`${name} 分布与均值±1σ`:`${name} 单点与均值`;chart.titleTextStyle.fontSize=13;chart.titleTextStyle.typeface='Arial';chart.hasLegend=false;
  chart.xAxis={title:{text:'水平位置仅用于错开重叠点'},numberFormatCode:';;;',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:11}};
  chart.yAxis={title:{text:`${name} (${result.unit})`},numberFormatCode:'0.000',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:11}};
  chart.setPosition('A10','J25');chartManifest.push({sheet:s.name,series:entries});
 }else line(s,14,'本项没有可绘制的有效入选数据');
 views.push({sheet:s.name,range:'A1:J37',label:name});
 views.push({sheet:s.name,range:`A${Math.max(28,t.averageRow-3)}:Q${t.averageRow+1}`,label:`${name}_averages`});
}
const all=wb.worksheets.add('全部参数');width(all);const allTable=table(all,1,records);all.freezePanes.freezeRows(1);tableManifest.push(allTable);views.push({sheet:all.name,range:`A1:J${Math.min(allTable.bottom,18)}`,label:'all'});
if(selection.repeatedTests.repeatedPointCount){
 const kept=wb.worksheets.add('保留结果');width(kept);line(kept,2,'同一样品同一点：先比较PCE，与最高PCE相对差<5%时比较FF。每点保留一条完整记录。');
 const retainedIds=new Set(selection.repeatedTests.selectedIds),retained=table(kept,4,records.filter(r=>retainedIds.has(r.id)),{role:'retained',average:true});tableManifest.push(retained);kept.freezePanes.freezeRows(4);
 const audit=wb.worksheets.add('重复测试对比');width(audit);line(audit,2,'相对差 = |本次PCE−同点最高PCE| / 较小PCE。严格<5%进入FF比较；恰好5%选PCE高者。保留状态为本次择优结果，修改原值后须重新运行择优。');
 const groups=selection.repeatedTests.groups.filter(g=>g.recordIds.length>1),groupById=new Map(groups.flatMap(g=>g.recordIds.map(id=>[id,g])));
 const comparison=table(audit,4,records.filter(r=>groupById.has(r.id)),{extras:[['同点最高PCE (%)',()=>null],['与最高PCE相对差',()=>null]],role:'repeat-comparison'});tableManifest.push(comparison);
 const pceIndex=comparison.metricFields.find(f=>f.key==='Efficiency (%)').index,positionById=new Map(comparison.positions.map(p=>[p.id,p]));
 const formulas={},expectedValues={};
 for(const p of comparison.positions){
  const group=groupById.get(p.id),refs=group.recordIds.map(id=>tableRef(comparison,positionById.get(id),pceIndex)),own=tableRef(comparison,p,pceIndex),maxRef=tableRef(comparison,p,comparison.labels.indexOf('同点最高PCE (%)')),gapRef=tableRef(comparison,p,comparison.labels.indexOf('与最高PCE相对差'));
  formulas[maxRef]=`=IF(COUNT(${refs.join(',')})=0,"无法计算",MAX(${refs.join(',')}))`;
  formulas[gapRef]=`=IF(COUNT(${own},${maxRef})<2,"无法计算",IF(${own}=${maxRef},0,IF(MIN(${own},${maxRef})<=0,"无法计算",ABS(${own}-${maxRef})/MIN(${own},${maxRef}))))`;
  const valid=group.recordIds.map(id=>byId.get(id).meta['Efficiency (%)']).filter(v=>typeof v==='number'&&Number.isFinite(v));
  expectedValues[maxRef]=valid.length?Math.max(...valid):null;expectedValues[gapRef]=group.relativeGaps[String(p.id)]??null;
  for(const ref of [maxRef,gapRef])audit.getRange(ref).formulas=[[formulas[ref]]];
  audit.getRange(maxRef).setNumberFormat('0.00000"%"');audit.getRange(gapRef).setNumberFormat('0.00000000%');
 }
 statisticsManifest.push({sheet:audit.name,formulas,expectedValues});audit.freezePanes.freezeRows(4);
 views.push({sheet:kept.name,range:`A1:O${Math.min(retained.bottom,18)}`,label:'retained'},{sheet:audit.name,range:`A1:J${Math.min(comparison.bottom,18)}`,label:'repeat-comparison'});
}
const raw=wb.worksheets.add('全部原始扫描');raw.showGridLines=false;
const rawHeaders=['V (V)','I (mA)','J (mA/cm²)','CSV行号'];
const textWidth=value=>[...String(value)].reduce((n,ch)=>n+(ch.charCodeAt(0)>255?1.7:1),0);
let titleHeight=30,sourceHeight=18,maxRawRow=4;
for(const [index,r] of records.entries()){
 const points=r.points||[],column=1+index*5,start=4,end=start+points.length-1,lastColumn=column+3;
 if(lastColumn>16384||end>1048576)throw new Error('Side-by-side raw scans exceed Excel dimensions; split the workbook scope');
 const left=col(column),right=col(lastColumn),body=`${left}${start}:${right}${Math.max(start,end)}`;
 base(raw,`${left}1:${right}${Math.max(start,end)}`);
 const values=points.map(p=>[p.v,p.i,p.j,p.row]);
 const widths=rawHeaders.map((label,c)=>Math.max(8,textWidth(label),...values.map(v=>textWidth(c===3?String(v[c]):v[c].toFixed(6))))+1.2);
 widths.forEach((w,c)=>raw.getRange(`${col(column+c)}:${col(column+c)}`).format.columnWidth=w);
 const title=`${r.id} / ${r.label}\n${r.meta['Time stamp']||'测试时间未提供'}（原扫描顺序）`,source=r.sourceLocation||'来源未提供';
 const capacity=widths.reduce((a,b)=>a+b,0)-3;
 for(const [row,text] of [[1,title],[2,source]]){raw.getRange(`${left}${row}:${right}${row}`).merge();raw.getRange(`${left}${row}`).values=[[text]];raw.getRange(`${left}${row}:${right}${row}`).format.wrapText=true;}
 titleHeight=Math.max(titleHeight,4+13*title.split('\n').reduce((n,t)=>n+Math.max(1,Math.ceil(textWidth(t)/capacity)),0));
 sourceHeight=Math.max(sourceHeight,4+13*source.split('\n').reduce((n,t)=>n+Math.max(1,Math.ceil(textWidth(t)/capacity)),0));
 raw.getRange(`${left}3:${right}3`).values=[rawHeaders];header(raw,`${left}3:${right}3`);
 if(points.length){raw.getRange(body).values=values;raw.getRange(`${left}${start}:${col(column+2)}${end}`).setNumberFormat('0.000000');raw.getRange(`${right}${start}:${right}${end}`).setNumberFormat('0');box(raw,body);raw.getRange(body).conditionalFormats.addCustom(`MOD(ROW()-${start},2)=1`,{fill:'#E8F0FA'});}
 if(index<records.length-1)raw.getRange(`${col(lastColumn+1)}:${col(lastColumn+1)}`).format.columnWidth=2;
 rawManifest.push({id:r.id,column,start,end,count:points.length,widths});maxRawRow=Math.max(maxRawRow,end);
}
if(records.length){const last=col(records.length*5-1);raw.getRange(`A4:${last}${maxRawRow}`).format.rowHeight=17;raw.getRange(`A1:${last}1`).format.rowHeight=titleHeight;raw.getRange(`A2:${last}2`).format.rowHeight=sourceHeight;raw.getRange(`A3:${last}3`).format.rowHeight=20;}
raw.freezePanes.freezeRows(3);views.push({sheet:raw.name,range:`A1:${col(Math.min(14,Math.max(4,records.length*5-1)))}18`,label:'raw'});
const summaryPrefix=[...fields.slice(0,11).map(f=>f[0]),'良品率 (a/b)',fields[11][0]];
const summaryManifest={sheet:overview.name,prefix:summaryPrefix,sections:[],cells:{},pointCountHelpers:[]};
const summaryHeaders=[...summaryPrefix,'Jsc入选n','Voc入选n','FF入选n','PCE入选n','Jsc CV (%)','Voc CV (%)','FF CV (%)','PCE CV (%)','提示','总测试点数 b'];
const pceSummaryHeaders=[...summaryPrefix,'PCE入选n','PCE CV (%)','面积 (cm²)','提示','总测试点数 b'];
const bottom=12+2*selection.scopes.length;
base(overview,`A1:W${bottom}`);overview.tabColor=ink;overview.getRange('A:A').format.columnWidth=29;overview.getRange('B:W').format.columnWidth=15;overview.getRange('L:L').format.columnWidth=22;overview.getRange('M:M').format.columnWidth=23;overview.getRange('V:V').format.columnWidth=40;
function summaryLine(row,text){overview.getRange(`A${row}:W${row}`).merge();overview.getRange(`A${row}`).values=[[text]];overview.getRange(`A${row}:W${row}`).format={wrapText:true,rowHeight:30};}
function summaryFormula(ref,formula,expectedValue){overview.getRange(ref).formulas=[[formula]];summaryManifest.cells[ref]={formula,expectedValue};}
function scopeDates(scope,ids){const chosen=new Set(ids||scope.recordIds);return [...new Set(records.filter(r=>chosen.has(r.id)).map(r=>(r.meta['Time stamp']||'').split(' ')[0]).filter(Boolean))].sort().join('、')||'未提供';}
// Denominator counts physical sample/point groups, including groups with no valid metric.
const allPositions=new Map(allTable.positions.map(p=>[p.id,p])),idIndex=allTable.labels.indexOf('记录ID');
const pointRanges=new Map();let helperRow=bottom+4;
overview.getRange(`A${helperRow}:F${helperRow}`).values=[['总测试点计数依据','条件','样品编号','测试点','计数（含无效点）','原始记录ID']];header(overview,`A${helperRow}:F${helperRow}`);helperRow++;
for(const scope of selection.scopes){
 const scopeIds=new Set(scope.recordIds),groups=selection.repeatedTests.groups.filter(g=>g.recordIds.some(id=>scopeIds.has(id))),first=helperRow,entries=[];
 for(const group of groups){
  const ids=group.recordIds.filter(id=>scopeIds.has(id)),refs=ids.map(id=>`'全部参数'!${tableRef(allTable,allPositions.get(id),idIndex)}`),formula=`=IF(COUNT(${refs.join(',')})>0,1,0)`;
  overview.getRange(`A${helperRow}:F${helperRow}`).values=[['同样品同点的重复测量合并一次',scope.label,group.sampleId,group.pointId,null,ids.join(',')]];
  summaryFormula(`E${helperRow}`,formula,1);entries.push({row:helperRow,recordIds:ids});helperRow++;
 }
 const last=Math.max(first,helperRow-1),range=`E${first}:E${last}`;pointRanges.set(scope.label,range);summaryManifest.pointCountHelpers.push({label:scope.label,range,entries});
}
base(overview,`A${bottom+5}:F${Math.max(bottom+5,helperRow-1)}`);overview.getRange(`A${bottom+5}:F${Math.max(bottom+5,helperRow-1)}`).format.wrapText=true;
function usableCount(result,sheet,stats){
 const tests=[`ISNUMBER('${sheet}'!H4)`,`'${sheet}'!H4<='${sheet}'!$L$4`];
 if(stats.gapIndex>=0){const first=tableManifest.find(t=>t.sheet===sheet&&t.role==='selected').positions[0]?.row??29,last=tableManifest.find(t=>t.sheet===sheet&&t.role==='selected').positions.at(-1)?.row??29;tests.push(`MAX('${sheet}'!$${col(stats.gapIndex+1)}$${first}:$${col(stats.gapIndex+1)}$${last})<='${sheet}'!$L$5`);}
 return `IF(AND(${tests.join(',')}),COUNT('${sheet}'!${stats.selectedRange}),0)`;
}
summaryLine(1,'四项独立筛选结果总结');summaryLine(2,'四项分别引用各自筛选均值，集合可以不同。良品率分别列a/b；b按同样品同点合并重复测量，无效点仍计入。CV=总体标准差÷均值绝对值。');
const secondTitle=6+selection.scopes.length,secondHeader=secondTitle+2;
summaryLine(secondTitle,'PCE筛选后的全部参数总结');summaryLine(secondTitle+1,'全部参数引用同一PCE入选集合的平均值。良品率a为PCE筛选后可用点数，b为本条件总样品点数（合并重复测量，含无效点）。');
for(const [kind,start] of [['independent',4],['pce',secondHeader]]){
 const heads=kind==='pce'?pceSummaryHeaders:summaryHeaders,lastCol=col(heads.length),bColumn=kind==='pce'?'R':'W';
 overview.getRange(`A${start}:${lastCol}${start}`).values=[heads];header(overview,`A${start}:${lastCol}${start}`);overview.getRange(`A${start}:${lastCol}${start}`).format.rowHeight=44;
 const section={kind,start,rows:[]};summaryManifest.sections.push(section);
 for(const [i,scope] of selection.scopes.entries()){
  const row=start+1+i;overview.getRange(`A${row}:${lastCol}${row}`).format={fill:i%2?'#E8F0FA':'#FFFFFF',rowHeight:kind==='independent'?62:28};box(overview,`A${row}:${lastCol}${row}`);overview.getRange(`A${row}`).values=[[scope.label]];
  const pce=selection.metrics[scope.metricNames.PCE],pceSheet=scope.metricNames.PCE+'筛选',pceTable=tableManifest.find(t=>t.sheet===pceSheet&&t.role==='selected');
  overview.getRange(`M${row}`).values=[[scopeDates(scope,kind==='pce'?pce.selectedIds:null)]];
  const bRef=`${bColumn}${row}`;summaryFormula(bRef,`=SUM(${pointRanges.get(scope.label)})`,scope.totalPointCount);
  section.rows.push({row,label:scope.label,metricNames:scope.metricNames,pceIds:pce.selectedIds,totalPointCount:scope.totalPointCount,bRef});
  const usable=new Map();
  for(const [j,metric] of ['Jsc','Voc','FF','PCE'].entries()){
   const name=scope.metricNames[metric],result=selection.metrics[name],sheet=name+'筛选',stats=statisticsManifest.find(st=>st.sheet===sheet);usable.set(metric,usableCount(result,sheet,stats));
   if(kind==='independent'){
    summaryFormula(`${col(j+2)}${row}`,`='${sheet}'!B4`,result.mean??'无法计算');
    summaryFormula(`${col(j+14)}${row}`,`=COUNT('${sheet}'!${stats.selectedRange})`,result.count);
    summaryFormula(`${col(j+18)}${row}`,`='${sheet}'!H4`,result.relativeRmse??'无法计算');
   }
  }
  let yieldFormula,yieldExpected;
  if(kind==='pce'){
   for(const [j,key] of keys.slice(0,10).entries()){
    const field=pceTable.metricFields.find(f=>f.key===key),ref=`${col(field.index+1)}${pceTable.averageRow}`,vals=pce.selectedIds.map(id=>byId.get(id).meta[key]).filter(v=>typeof v==='number'&&Number.isFinite(v));
    summaryFormula(`${col(j+2)}${row}`,`='${pceSheet}'!${ref}`,vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:'无法计算');
   }
   const stats=statisticsManifest.find(st=>st.sheet===pceSheet);summaryFormula(`N${row}`,`=COUNT('${pceSheet}'!${stats.selectedRange})`,pce.count);summaryFormula(`O${row}`,`='${pceSheet}'!H4`,pce.relativeRmse??'无法计算');
   const field=pceTable.metricFields.find(f=>f.key==='Area (cm^2)'),areaRef=`${col(field.index+1)}${pceTable.averageRow}`,areas=pce.selectedIds.map(id=>byId.get(id).meta['Area (cm^2)']).filter(v=>typeof v==='number'&&Number.isFinite(v));
   summaryFormula(`P${row}`,`='${pceSheet}'!${areaRef}`,areas.length?areas.reduce((a,b)=>a+b,0)/areas.length:'无法计算');
   summaryFormula(`Q${row}`,`=IF(N${row}=0,"无有效PCE",IF(N${row}=1,"仅1点，无法评价离散性",""))`,pce.count===0?'无有效PCE':pce.count===1?'仅1点，无法评价离散性':'');
   yieldFormula=`=IF(${bRef}=0,"无法计算（总测试点数为0）",${usable.get('PCE')}&"/"&${bRef})`;yieldExpected=`${pce.passed?pce.count:0}/${scope.totalPointCount}`;
  }else{
   const single=['Jsc','Voc','FF','PCE'].some(metric=>selection.metrics[scope.metricNames[metric]].count===1);
   summaryFormula(`V${row}`,`=IF(COUNTIFS(N${row}:Q${row},1)>0,"存在单点指标，无法评价其离散性","")`,single?'存在单点指标，无法评价其离散性':'');
   yieldFormula=`=IF(${bRef}=0,"无法计算（总测试点数为0）",`+['Jsc','Voc','FF','PCE'].map(metric=>`"${metric} "&${usable.get(metric)}&"/"&${bRef}`).join('&CHAR(10)&')+')';
   yieldExpected=['Jsc','Voc','FF','PCE'].map(metric=>{const result=selection.metrics[scope.metricNames[metric]];return `${metric} ${result.passed?result.count:0}/${scope.totalPointCount}`;}).join(String.fromCharCode(10));
  }
  summaryFormula(`L${row}`,yieldFormula,scope.totalPointCount?yieldExpected:'无法计算（总测试点数为0）');overview.getRange(`L${row}`).format.wrapText=true;overview.getRange(`L${row}`).setNumberFormat('@');
  overview.getRange(`B${row}:K${row}`).setNumberFormat('0.00000');overview.getRange(`D${row}:E${row}`).setNumberFormat('0.00000"%"');overview.getRange(bRef).setNumberFormat('0');
  if(kind==='independent'){overview.getRange(`N${row}:Q${row}`).setNumberFormat('0');overview.getRange(`R${row}:U${row}`).setNumberFormat('0.00000%');}else{overview.getRange(`N${row}`).setNumberFormat('0');overview.getRange(`O${row}`).setNumberFormat('0.00000%');overview.getRange(`P${row}`).setNumberFormat('0.00000');}
 }
}
views.unshift({sheet:overview.name,range:`A1:W${bottom}`,label:'summary'});
wb.recalculate();console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:10},maxChars:1200})).ndjson);await (await SpreadsheetFile.exportXlsx(wb)).save(output);
const manifest={version:8,chartManifest,tableManifest,rawManifest,statisticsManifest,summaryManifest,selection};await fs.writeFile(`${output}.manifest.json`,JSON.stringify(manifest,null,2));
run('finalize_workbook.py',['--data',input,'--manifest',`${output}.manifest.json`,'--workbook',output]);
if(options['--preview-dir']){const dir=path.resolve(options['--preview-dir']);await fs.mkdir(dir,{recursive:true});const final=await SpreadsheetFile.importXlsx(await FileBlob.load(output));for(const view of views){const png=await final.render({sheetName:view.sheet,range:view.range,scale:1.3,format:'png'});await fs.writeFile(path.join(dir,`${view.label}_preview.png`),new Uint8Array(await png.arrayBuffer()));}}
console.log(JSON.stringify({saved:output,records:records.length,distributionCharts:chartManifest.length,jvCurves:0}));
