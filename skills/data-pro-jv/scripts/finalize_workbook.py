"""Verify vertical tables/scans and repair native distribution-chart export."""
import argparse
import json
import math
import posixpath
import re
import zipfile
import xml.etree.ElementTree as E
from pathlib import Path
from select_metrics import select_all

NS={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart',
    'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
    's':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
for prefix in ('c','a'):E.register_namespace(prefix,NS[prefix])


def close(a,b):
    return math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-12)


def column(n):
    result=''
    while n:
        n,rem=divmod(n-1,26)
        result=chr(65+rem)+result
    return result


def col_number(label):
    n=0
    for ch in label:n=n*26+ord(ch)-64
    return n


def verify(workbook,manifest,data):
    assert manifest.get('version')==9,'Use the version 9 condition maxima, physical-point yield and two-summary manifest'
    expected=select_all(data)
    assert manifest['selection']==expected,'Input selection changed'
    records={r['id']:dict(r,**expected['repeatedTests']['annotations'][str(r['id'])]) for r in data['uniqueRecords']}
    with zipfile.ZipFile(workbook) as archive:
        assert archive.testzip() is None
        entries=[(info,archive.read(info.filename)) for info in archive.infolist()]
    payload={info.filename:body for info,body in entries}
    root=E.fromstring(payload['xl/workbook.xml'])
    targets={r.get('Id'):posixpath.normpath(posixpath.join('xl',r.get('Target'))) if not r.get('Target').startswith('/') else r.get('Target').lstrip('/') for r in E.fromstring(payload['xl/_rels/workbook.xml.rels'])}
    sheets={s.get('name'):targets[s.get('{'+NS['r']+'}id')] for s in root.findall('s:sheets/s:sheet',NS)}
    required={name+'筛选' for name in expected['metrics']}|{'总结','全部参数','全部原始扫描'}
    if expected['repeatedTests']['repeatedPointCount']:required.update({'保留结果','重复测试对比'})
    assert set(sheets)==required
    assert next(iter(sheets))=='总结','The first worksheet must contain both summaries'
    strings=[]
    if 'xl/sharedStrings.xml' in payload:
        strings=[''.join(t.text or '' for t in si.iter('{'+NS['s']+'}t')) for si in E.fromstring(payload['xl/sharedStrings.xml'])]
    cells={name:{c.get('r'):c for c in E.fromstring(payload[p]).findall('.//s:c',NS)} for name,p in sheets.items()}

    def value(sheet,ref):
        cell=cells[sheet].get(ref)
        if cell is None:return None
        v=cell.find('s:v',NS)
        if cell.get('t')=='s':return strings[int(v.text)]
        if cell.get('t')=='inlineStr':return ''.join(t.text or '' for t in cell.iter('{'+NS['s']+'}t'))
        if cell.get('t')=='e':raise ValueError(f'Formula error at {sheet}!{ref}')
        if cell.get('t')=='str':return (v.text or '') if v is not None else ''
        return v.text if v is not None else None

    def table_ref(table,position,index):
        assert table['orientation']=='rows','All parameter tables must be one test per row'
        return f"{column(index+1)}{position['row']}"

    for table in manifest['tableManifest']:
        assert table['orientation']=='rows'
        assert table['labels'][:12]==['编号','Jsc (mA/cm²)','Voc (V)','FF (%)','PCE (%)','Pmax (mW)','Imax (mA)','Vmax (V)','Rs (Ω)','Rsh (Ω)','Isc (mA)','日期']
        for index,label in enumerate(table['labels']):
            assert value(table['sheet'],f"{column(index+1)}{table['start']}")==label
        for p in table['positions']:
            rec=records[p['id']]
            for field in table['metricFields']:
                actual=value(table['sheet'],table_ref(table,p,field['index']))
                source=rec['meta'].get(field['key'])
                assert (actual is None and source is None) or (actual is not None and source is not None and close(actual,source)),(table['sheet'],p['id'],field['key'])
            assert value(table['sheet'],table_ref(table,p,table['sourceIndex']))==(rec.get('sourceLocation') or None)
            for label,key in [('样品编号','sampleId'),('测试点','pointId'),('保留状态','retentionStatus'),('择优依据','repeatReason')]:
                index=table['labels'].index(label)
                assert value(table['sheet'],table_ref(table,p,index))==rec.get(key)
        if table['role'] in ('selected','retained'):
            assert table['averageRow']==table['dataBottom']+1
            assert value(table['sheet'],f"A{table['averageRow']}")=='平均值（本表入选记录）'
            for field in table['metricFields']:
                letter=column(field['index']+1)
                refs=f"{letter}{table['start']+1}:{letter}{table['dataBottom']}"
                ref=f"{letter}{table['averageRow']}"
                formula=f'=IF(COUNT({refs})=0,"无法计算",AVERAGE({refs}))'
                assert table['averageFormulas'][ref]==formula
                cell=cells[table['sheet']].get(ref)
                assert cell is not None and cell.find('s:f',NS).text.lstrip('=')==formula.lstrip('=')
                values=[records[p['id']]['meta'].get(field['key']) for p in table['positions']]
                values=[v for v in values if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)]
                actual=value(table['sheet'],ref)
                assert (not values and actual=='无法计算') or (values and close(actual,math.fsum(values)/len(values))),(table['sheet'],ref,actual,values)
    if expected['repeatedTests']['repeatedPointCount']:
        retained=next(t for t in manifest['tableManifest'] if t['role']=='retained')
        assert [p['id'] for p in retained['positions']]==expected['repeatedTests']['selectedIds']
        comparison=next(t for t in manifest['tableManifest'] if t['role']=='repeat-comparison')
        repeat_ids={i for g in expected['repeatedTests']['groups'] if len(g['recordIds'])>1 for i in g['recordIds']}
        assert [p['id'] for p in comparison['positions']]==[i for i in records if i in repeat_ids]
    assert len(manifest['statisticsManifest'])==len(expected['metrics'])+bool(expected['repeatedTests']['repeatedPointCount'])
    for statistics in manifest['statisticsManifest']:
        sheet=statistics['sheet']
        for ref,formula in statistics['formulas'].items():
            node=cells[sheet].get(ref)
            assert node is not None and node.find('s:f',NS) is not None,('Missing live formula',sheet,ref)
            assert node.find('s:f',NS).text.lstrip('=')==formula.lstrip('='),('Wrong formula',sheet,ref)
        for ref,expected_value in statistics.get('expectedValues',{}).items():
            actual=value(sheet,ref)
            assert (expected_value is None and actual=='无法计算') or (expected_value is not None and close(actual,expected_value)),(sheet,ref,actual,expected_value)
    for name,result in expected['metrics'].items():
        sheet=name+'筛选'
        for ref,v in [('B4',result['mean']),('B5',result['mse']),('H5',math.sqrt(result['mse']) if result['mse'] is not None else None),('H4',result['relativeRmse'])]:
            actual=value(sheet,ref)
            assert (actual=='无法计算' and v is None) or (actual is not None and v is not None and close(actual,v))
        table=next(t for t in manifest['tableManifest'] if t['sheet']==sheet and t['role']=='selected')
        statistics=next(st for st in manifest['statisticsManifest'] if st['sheet']==sheet)
        display_ids=[r['id'] for r in data['uniqueRecords'] if r['id'] in result['selectedIds']]
        assert [p['id'] for p in table['positions']]==display_ids,'Display must preserve original source order'
        for p in table['positions']:
            assert close(value(sheet,table_ref(table,p,statistics['metricIndex'])),records[p['id']]['meta'][result['key']])
            deviation=records[p['id']]['meta'][result['key']]-result['mean']
            assert close(value(sheet,table_ref(table,p,statistics['deviationIndex'])),deviation)
            assert close(value(sheet,table_ref(table,p,statistics['squareIndex'])),deviation**2)
            if statistics['gapIndex']>=0:
                assert close(value(sheet,table_ref(table,p,statistics['gapIndex'])),abs(result['bestValue']-records[p['id']]['meta'][result['key']]))
                assert abs(result['bestValue']-records[p['id']]['meta'][result['key']])<=result['maxAbsoluteGapAllowed']+1e-12
        assert set(result['bestIds'])<=set(result['selectedIds']),'Every tied candidate maximum must be retained'
    summary=manifest['summaryManifest']
    assert summary['sheet']=='总结' and [s['kind'] for s in summary['sections']]==['independent','pce']
    assert summary['prefix']==['编号','Jsc (mA/cm²)','Voc (V)','FF (%)','PCE (%)','Pmax (mW)','Imax (mA)','Vmax (V)','Rs (Ω)','Rsh (Ω)','Isc (mA)','良品率 (a/b)','日期']
    for section in summary['sections']:
        for index,label in enumerate(summary['prefix']):
            assert value('总结',f"{column(index+1)}{section['start']}")==label
        assert len(section['rows'])==len(expected['scopes'])
        for row,scope in zip(section['rows'],expected['scopes']):
            assert value('总结',f"A{row['row']}")==scope['label']
            groups=[g for g in expected['repeatedTests']['groups'] if any(i in scope['recordIds'] for i in g['recordIds'])]
            total=len(groups)
            assert total==scope['totalPointCount']==row['totalPointCount']
            assert close(value('总结',row['bRef']),total)
            if total==0:
                expected_yield='无法计算（总测试点数为0）'
            elif section['kind']=='pce':
                result=expected['metrics'][scope['metricNames']['PCE']]
                expected_yield=f"{result['count'] if result['passed'] else 0}/{total}"
            else:
                expected_yield='\n'.join(f"{name} {expected['metrics'][scope['metricNames'][name]]['count'] if expected['metrics'][scope['metricNames'][name]]['passed'] else 0}/{total}" for name in ['Jsc','Voc','FF','PCE'])
            assert value('总结',f"L{row['row']}")==expected_yield
            if section['kind']=='independent':
                for index,name in enumerate(['Jsc','Voc','FF','PCE'],2):
                    result=expected['metrics'][scope['metricNames'][name]]
                    actual=value('总结',f"{column(index)}{row['row']}")
                    assert (result['mean'] is None and actual=='无法计算') or close(actual,result['mean'])
                assert all(value('总结',f"{column(index)}{row['row']}") is None for index in range(6,12))
            else:
                result=expected['metrics'][scope['metricNames']['PCE']]
                assert row['pceIds']==result['selectedIds']
                keys=['Jsc (mA/cm^2)','Voc (V)','Fill Factor (%)','Efficiency (%)','Pmax (mW)','Imax (mA)','Vmax (V)','Rs (ohm)','Rsh (ohm)','Isc (mA)']
                for index,key in enumerate(keys,2):
                    vals=[records[i]['meta'].get(key) for i in result['selectedIds']]
                    vals=[v for v in vals if isinstance(v,(float,int)) and math.isfinite(v)]
                    actual=value('总结',f"{column(index)}{row['row']}")
                    assert (not vals and actual=='无法计算') or (vals and close(actual,math.fsum(vals)/len(vals)))
    maximum_specs=summary.get('maximumCells',[])
    assert len(maximum_specs)==4*len(expected['scopes']),'Every condition needs four maximum values'
    all_table=next(t for t in manifest['tableManifest'] if t['sheet']=='全部参数')
    all_positions={p['id']:p for p in all_table['positions']}
    retained=set(expected['repeatedTests']['selectedIds'])
    independent=next(s for s in summary['sections'] if s['kind']=='independent')
    for row,scope in zip(independent['rows'],expected['scopes']):
        candidate_ids=[r['id'] for r in data['uniqueRecords'] if r['id'] in scope['recordIds'] and r['id'] in retained]
        for offset,(metric,key,label) in enumerate([
            ('Jsc','Jsc (mA/cm^2)','Jsc最大值 (mA/cm²)'),
            ('Voc','Voc (V)','Voc最大值 (V)'),
            ('FF','Fill Factor (%)','FF最大值 (%)'),
            ('PCE','Efficiency (%)','PCE最大值 (%)')]):
            ref=f"{column(24+offset)}{row['row']}"
            assert value('总结',f"{column(24+offset)}{independent['start']}")==label
            spec=next(s for s in maximum_specs if s['ref']==ref)
            assert spec['conditionLabel']==scope['label'] and spec['metric']==metric and spec['key']==key
            assert spec['recordIds']==candidate_ids
            field=next(f for f in all_table['metricFields'] if f['key']==key)
            refs=','.join(f"'全部参数'!{table_ref(all_table,all_positions[i],field['index'])}" for i in candidate_ids)
            formula=f'=IF(COUNT({refs})=0,"无法计算",MAX({refs}))' if refs else '="无法计算"'
            assert spec['formula']==summary['cells'][ref]['formula']==formula
            values=[records[i]['meta'].get(key) for i in candidate_ids]
            values=[v for v in values if isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v)]
            actual=value('总结',ref)
            assert (not values and actual=='无法计算') or (values and close(actual,max(values)))
    for ref,spec in summary['cells'].items():
        node=cells['总结'][ref]
        assert node.find('s:f',NS).text.lstrip('=')==spec['formula'].lstrip('=')
        actual=value('总结',ref)
        assert (actual==spec['expectedValue']) if isinstance(spec['expectedValue'],str) else close(actual,spec['expectedValue'])
    assert [r['id'] for r in manifest['rawManifest']]==list(records)
    for index,raw in enumerate(manifest['rawManifest']):
        points=records[raw['id']].get('points',[])
        assert raw['count']==len(points)
        assert raw['column']==1+index*5 and raw['start']==4,'Scans must start together and be arranged left to right'
        assert [value('全部原始扫描',f"{column(raw['column']+c)}3") for c in range(4)]==['V (V)','I (mA)','J (mA/cm²)','CSV行号']
        for row,point in enumerate(points,raw['start']):
            for c,key in enumerate(('v','i','j','row'),raw['column']):
                assert close(value('全部原始扫描',f'{column(c)}{row}'),point[key])
    for sheet,refs in cells.items():
        for ref,cell in refs.items():
            if cell.get('t')=='e':raise ValueError(f'Formula error at {sheet}!{ref}')

    def range_values(formula):
        m=re.fullmatch(r"'(.+)'!\$([A-Z]+)\$(\d+):\$([A-Z]+)\$(\d+)",formula)
        assert m,formula
        a,b=col_number(m[2]),col_number(m[4])
        ra,rb=int(m[3]),int(m[5])
        assert a==b or ra==rb,'Series must be a single row or column'
        return [value(m[1],f'{column(c)}{r}') for r in range(ra,rb+1) for c in range(a,b+1)]

    charts={entry['sheet']:entry for entry in manifest['chartManifest']}
    chart_files=[name for name in payload if '/charts/' in name and name.endswith('.xml')]
    assert len(chart_files)==len(charts)
    tag=lambda name:'{'+NS['c']+'}'+name
    patches={}
    for filename in chart_files:
        chart=E.fromstring(payload[filename])
        scatter=chart.find('.//c:scatterChart',NS)
        assert scatter is not None,'Expected native XY distribution chart'
        series_list=scatter.findall('c:ser',NS)
        first_x=series_list[0].find('c:xVal/c:numRef/c:f',NS).text
        sheet=re.match(r"'(.+)'!",first_x)[1]
        entry=charts.pop(sheet)
        assert len(series_list)==len(entry['series'])
        result=expected['metrics'][sheet[:-2]]
        selected=[r for r in data['uniqueRecords'] if r['id'] in result['selectedIds']]
        dot=entry['series'][0]
        assert dot['kind']=='points' and dot['ids']==[r['id'] for r in selected]
        assert dot['y']==[r['meta'][result['key']] for r in selected]
        assert all(close(x,1+(((i*.618033988749895)%1)-.5)*.24) for i,x in enumerate(dot['x']))
        scatter.find('c:scatterStyle',NS).set('val','lineMarker')
        for index,(series,spec) in enumerate(zip(series_list,entry['series'])):
            for axis in ('x','y'):
                ref=series.find('c:'+axis+'Val/c:numRef',NS)
                formula=spec[axis+'Formula']
                exported=ref.find('c:f',NS).text
                seed=f"'{sheet}'!${'L' if axis=='x' else column(13+index)}$11:${'L' if axis=='x' else column(13+index)}$12"
                assert exported in (formula,seed),(sheet,index,axis,exported)
                ref.find('c:f',NS).text=formula
                actual=range_values(formula)
                assert len(actual)==len(spec[axis]) and all(close(a,b) for a,b in zip(actual,spec[axis]))
                cache=ref.find('c:numCache',NS)
                if cache is None:cache=E.SubElement(ref,tag('numCache'))
                cache.clear();E.SubElement(cache,tag('formatCode')).text='0.00000000'
                E.SubElement(cache,tag('ptCount'),{'val':str(len(actual))})
                for i,v in enumerate(actual):
                    point=E.SubElement(cache,tag('pt'),{'idx':str(i)});E.SubElement(point,tag('v')).text=format(float(v),'.16g')
            if spec['kind']=='mean':assert all(close(v,result['mean']) for v in spec['y'])
            if spec['kind']=='sd':
                sigma=math.sqrt(result['mse'])
                assert len(selected)>=2 and all(close(a,b) for a,b in zip(spec['y'],[result['mean']-sigma,result['mean']+sigma]))
            color={'points':'2563EB','mean':'15803D','sd':'D97706'}[spec['kind']]
            for old in series.findall('c:marker',NS):series.remove(old)
            marker=E.Element(tag('marker'));E.SubElement(marker,tag('symbol'),{'val':'circle' if spec['kind']=='points' else 'dash' if spec['kind']=='sd' else 'none'})
            E.SubElement(marker,tag('size'),{'val':'6' if spec['kind']=='points' else '10'})
            marker_shape=E.SubElement(marker,tag('spPr'));fill=E.SubElement(marker_shape,'{'+NS['a']+'}solidFill');E.SubElement(fill,'{'+NS['a']+'}srgbClr',{'val':color})
            series.insert(list(series).index(series.find('c:xVal',NS)),marker)
            shape=series.find('c:spPr',NS)
            if shape is None:shape=E.Element(tag('spPr'));series.insert(2,shape)
            for old in shape.findall('a:ln',NS):shape.remove(old)
            line=E.SubElement(shape,'{'+NS['a']+'}ln',{'w':'25400'})
            if spec['kind']=='points':E.SubElement(line,'{'+NS['a']+'}noFill')
            else:
                fill=E.SubElement(line,'{'+NS['a']+'}solidFill');E.SubElement(fill,'{'+NS['a']+'}srgbClr',{'val':color})
            smooth=series.find('c:smooth',NS)
            if smooth is None:smooth=E.SubElement(series,tag('smooth'))
            smooth.set('val','0')
        patches[filename]=E.tostring(chart,encoding='utf-8',xml_declaration=True)
    assert not charts
    temporary=workbook.with_name(workbook.name+'.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for info,body in entries:archive.writestr(info,patches.get(info.filename,body))
    temporary.replace(workbook)
    with zipfile.ZipFile(workbook) as archive:
        assert archive.testzip() is None
        for filename in chart_files:
            chart=E.fromstring(archive.read(filename));series=chart.findall('.//c:scatterChart/c:ser',NS)
            assert series[0].find('c:marker/c:symbol',NS).get('val')=='circle'
            assert series[0].find('c:spPr/a:ln/a:noFill',NS) is not None
            assert all(s.find('c:smooth',NS).get('val')=='0' for s in series)
            for s in series:
                for axis in ('x','y'):assert '$L$11' not in s.find('c:'+axis+'Val/c:numRef/c:f',NS).text
    return dict(verifiedDistributionCharts=len(chart_files),verticalParameterTables=len(manifest['tableManifest']),verticalRawScans=len(manifest['rawManifest']),jvCurves=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',required=True,type=Path);parser.add_argument('--manifest',required=True,type=Path);parser.add_argument('--workbook',required=True,type=Path)
    args=parser.parse_args()
    data=json.loads(args.data.read_text(encoding='utf-8-sig'));manifest=json.loads(args.manifest.read_text(encoding='utf8'))
    print(json.dumps(verify(args.workbook,manifest,data)))


if __name__=='__main__':main()
