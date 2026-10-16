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
const records=data.uniqueRecords,byId=new Map(records.map(r=>[r.id,r])),inputIndex=new Map(records.map((r,i)=>[r.id,i]));
const wb=Workbook.create(),ink='#183153',blue='#2563EB';
const keys=['Jsc (mA/cm^2)','Voc (V)','Efficiency (%)','Fill Factor (%)','Pmax (mW)','Imax (mA)','Vmax (V)','Rs (ohm)','Rsh (ohm)','Area (cm^2)','Isc (mA)'];
const labels=['Jsc (mA/cm²)','Voc (V)','PCE (%)','FF (%)','Pmax (mW)','Imax (mA)','Vmax (V)','Rs (Ω)','Rsh (Ω)','面积 (cm²)','Isc (mA)'];
const fields=[['文件名 / 原始测试点名',r=>r.label],['记录ID',r=>r.id],...keys.map((k,i)=>[labels[i],r=>r.meta[k]??null,k]),
 ['原始组号',r=>r.meta.group??null],['测试时间',r=>r.meta['Time stamp']??null],['样品编号',r=>r.sampleId??r.cell??null],['测量组/次数',r=>r.measurementGroup??r.file??null],
 ['保留状态',r=>r.retentionStatus??null],['异常标记',r=>r.anomalyFlag??null],['异常依据',r=>r.anomalyReason??null],['所属结果组',r=>(r.resultGroups||[]).join('\n')],
 ['优选关注',r=>r.recommendation||null],['文件名称 / 位置（含重复来源）',r=>r.sourceLocation||null]];
function col(n){let s='';for(;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;}
function base(s,range){s.showGridLines=false;s.getRange(range).format={font:{name:'Arial',size:10,color:ink},rowHeight:20,horizontalAlignment:'center',verticalAlignment:'center'};}
function box(s,range){s.getRange(range).format.borders={preset:'all',style:'thin',color:'#94A3B8'};}
function header(s,range){s.getRange(range).format={fill:ink,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:30};box(s,range);}
function line(s,row,text){s.getRange(`A${row}:J${row}`).merge();s.getRange(`A${row}`).values=[[text]];s.getRange(`A${row}:J${row}`).format.wrapText=true;s.getRange(`A${row}:J${row}`).format.rowHeight=Math.max(24,Math.ceil([...text].length/70)*17);}
function width(s){s.getRange('A:A').format.columnWidth=26;s.getRange('B:J').format.columnWidth=12;}
function lines(value,width){return typeof value==='string'?value.split('\n').reduce((n,t)=>n+Math.max(1,Math.ceil([...t].length/(width/1.6))),0):1;}
function table(s,start,items,{extras=[],role='parameters'}={}){
 const defs=[fields[0],...extras,...fields.slice(1)],positions=[],separators=[];let cursor=start+1,lastGroup=null;
 for(const r of items){
  const group=r.sampleId??r.groupKey??r.cell;
  if(lastGroup!==null&&group!==lastGroup){separators.push(cursor);cursor++;}
  positions.push({id:r.id,row:cursor});lastGroup=group;cursor++;
 }
 const end=defs.length,bottom=Math.max(start+1,cursor-1);
 if(end>16384||bottom>1048576)throw new Error('Table exceeds Excel dimensions; split scope');
 base(s,`A${start}:${col(end)}${bottom}`);
 s.getRange(`A${start}:${col(end)}${start}`).values=[defs.map(d=>d[0])];header(s,`A${start}:${col(end)}${start}`);
 defs.forEach(([label],i)=>s.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=i===0?29:label.startsWith('文件名称')?48:label==='优选关注'?32:label==='测试时间'?21:label==='未入选原因'?28:12);
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
  s.getRange(range).format.rowHeight=Math.min(409,Math.max(22,...values.map((v,i)=>4+13*lines(v,i===0?29:defs[i][0].startsWith('文件名称')?48:defs[i][0]==='优选关注'?32:defs[i][0]==='测试时间'?21:12))));
 }
 for(const gap of separators){const r=`A${gap}:${col(end)}${gap}`;s.getRange(r).format.fill=ink;s.getRange(r).format.rowHeight=8;}
 if(!items.length)s.getRange(`A${start+1}`).values=[['无记录']];
 s.freezePanes.freezeColumns(1);
 return {sheet:s.name,start,bottom,end,orientation:'rows',role,positions,labels:defs.map(d=>d[0]),metricFields:defs.flatMap((d,i)=>d[2]?[{key:d[2],index:i}]:[]),sourceIndex:defs.length-1};
}
function tableRef(table,p,index){return `${col(index+1)}${p.row}`;}
const chartManifest=[],tableManifest=[],rawManifest=[],statisticsManifest=[],views=[];
for(const [name,result] of Object.entries(selection.metrics)){
 const s=wb.worksheets.add(`${name}筛选`);base(s,'A1:J26');width(s);s.tabColor=ink;
 line(s,2,`${name} 入选数据分布`);s.getRange('A2').format.font={name:'Arial',size:14,bold:true,color:ink};
 s.getRange('A4').values=[[`最终均值 (${result.unit})`]];s.getRange('B4:C4').merge();
 s.getRange('D4:G4').merge();s.getRange('D4').values=[['相对均方根偏差（用户所称MSE）']];s.getRange('H4:J4').merge();
 s.getRange('A4:J4').format.rowHeight=35;s.getRange('B4:C4').format.font={name:'Arial',size:14,bold:true,color:blue};s.getRange('H4:J4').format.font={name:'Arial',size:14,bold:true,color:blue};
 s.getRange('B4').setNumberFormat(result.unit==='%'?'0.00000"%"':'0.00000');s.getRange('H4').setNumberFormat('0.00000000%');
 s.getRange('A5').values=[[`原始MSE (${result.unit==='%'?'百分点²':`(${result.unit})²`})`]];s.getRange('B5:C5').merge();s.getRange('D5:G5').merge();s.getRange('D5').values=[[`总体标准差 σ (${result.unit==='%'?'百分点':result.unit})`]];s.getRange('H5:J5').merge();s.getRange('B5').setNumberFormat('0.00000000');s.getRange('H5').setNumberFormat('0.00000000');s.getRange('A5:J5').format.rowHeight=25;
 const sigma=result.mse===null?null:Math.sqrt(result.mse);
 line(s,6,`${data.conditionLabel?data.conditionLabel+'。':''}入选 ${result.count} / 有效 ${result.validCount} / 候选 ${result.candidateCount}。${result.status}。范围：${data.files.join('、')}`);
 line(s,7,'相对均方根偏差 = √[Σ(x−均值)²/n] ÷ |均值|，严格 < 5%。修改入选值后公式自动重算；重新筛选需重新运行处理。');
 const spreadNote=result.count>=2?'橙线：均值±1σ（标准差见H5，分母为n）。':'入选少于2点，不显示标准差标记。';
 line(s,8,`蓝点：入选原始值；绿线：均值；${spreadNote}横向位置仅用于错开重叠点。`);
 if(!result.passed||result.count<2)s.getRange('A6:J6').format.fill='#FEF3C7';
 const ids=new Set(result.selectedIds),selected=records.filter(r=>ids.has(r.id));
 const t=table(s,28,selected,{extras:[['原始测量序号',(_,i)=>i+1],[`${name}入选原值 (${result.unit})`,r=>r.meta[result.key]],[`与均值之差 (${result.unit})`,()=>null],[`偏差平方 ((${result.unit})²)`,()=>null]],role:'selected'});tableManifest.push(t);
 const first=t.positions[0]?.row??29,last=t.positions.at(-1)?.row??29,selectedRange=`$C$${first}:$C$${last}`,squareRange=`$E$${first}:$E$${last}`;
 const formulas={B4:`=IF(COUNT(${selectedRange})=0,"无法计算",AVERAGE(${selectedRange}))`,B5:`=IF(COUNT(${selectedRange})=0,"无法计算",SUM(${squareRange})/COUNT(${selectedRange}))`,H5:`=IF(COUNT(${selectedRange})=0,"无法计算",SQRT(B5))`,H4:`=IF(COUNT(${selectedRange})=0,"无法计算",IF(B4=0,"无法计算",H5/ABS(B4)))`};
 const literal=text=>`"${String(text).replaceAll('"','""')}"`;
 formulas.A6=`=${literal(`${data.conditionLabel?data.conditionLabel+'。':''}当前参与计算 `)}&COUNT(${selectedRange})&${literal(` / 本次候选 ${result.candidateCount}。`)}&IF(COUNT(${selectedRange})=0,"无有效值，无法计算",IF(B4=0,"均值为0，相对偏差无法计算",IF(COUNT(${selectedRange})=1,"仅1点，无法评价离散性",IF(H4<0.05,"相对均方根偏差 < 5%","相对均方根偏差 ≥ 5%，需重新筛选"))))&${literal(`。范围：${data.files.join('、')}`)}`;
 for(const [ref,formula] of Object.entries(formulas))s.getRange(ref).formulas=[[formula]];
 for(const p of t.positions){const ref=`C${p.row}`;formulas[`D${p.row}`]=`=${ref}-$B$4`;formulas[`E${p.row}`]=`=D${p.row}^2`;s.getRange(`D${p.row}:E${p.row}`).formulas=[[formulas[`D${p.row}`],formulas[`E${p.row}`]]];s.getRange(`D${p.row}:E${p.row}`).setNumberFormat('0.00000000');}
 const statistics={sheet:s.name,selectedRange,squareRange,formulas};statisticsManifest.push(statistics);
 for(const p of t.positions)if(result.bestIds.includes(p.id))s.getRange(tableRef(t,p,2)).format.fill='#FEF3C7';
 const excludedStart=t.bottom+3;line(s,excludedStart,'未入选原始数据（完整记录仍保留于全部参数）');
 const excluded=table(s,excludedStart+1,records.filter(r=>!ids.has(r.id)),{extras:[['未入选原因',r=>result.excludedReasons[String(r.id)]]],role:'excluded'});tableManifest.push(excluded);
 const helper=excluded.bottom+4;
 if(selected.length){
  const rawRefs=t.positions.map(p=>tableRef(t,p,2));
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
}
const all=wb.worksheets.add('全部参数');width(all);const allTable=table(all,1,records);all.freezePanes.freezeRows(1);tableManifest.push(allTable);views.push({sheet:all.name,range:`A1:J${Math.min(allTable.bottom,18)}`,label:'all'});
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
wb.recalculate();await (await SpreadsheetFile.exportXlsx(wb)).save(output);
const manifest={version:5,chartManifest,tableManifest,rawManifest,statisticsManifest,selection};await fs.writeFile(`${output}.manifest.json`,JSON.stringify(manifest,null,2));
run('finalize_workbook.py',['--data',input,'--manifest',`${output}.manifest.json`,'--workbook',output]);
if(options['--preview-dir']){const dir=path.resolve(options['--preview-dir']);await fs.mkdir(dir,{recursive:true});const final=await SpreadsheetFile.importXlsx(await FileBlob.load(output));for(const view of views){const png=await final.render({sheetName:view.sheet,range:view.range,scale:1.3,format:'png'});await fs.writeFile(path.join(dir,`${view.label}_preview.png`),new Uint8Array(await png.arrayBuffer()));}}
console.log(JSON.stringify({saved:output,records:records.length,distributionCharts:chartManifest.length,jvCurves:0}));
