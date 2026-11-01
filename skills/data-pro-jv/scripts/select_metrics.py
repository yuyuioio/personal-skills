"""Select high-value prefixes independently, retaining every tied maximum."""
import argparse
import json
import math
from decimal import Decimal, localcontext
from pathlib import Path
from select_repeated import select_repeated

METRICS = [('Jsc', 'Jsc (mA/cm^2)', 'mA/cm²'), ('Voc', 'Voc (V)', 'V'),
           ('FF', 'Fill Factor (%)', '%'), ('PCE', 'Efficiency (%)', '%')]
POLICIES = {
    'Jsc (mA/cm^2)': dict(threshold=0.008, maxAbsoluteGap=None),
    'Voc (V)': dict(threshold=0.008, maxAbsoluteGap=None),
    'Fill Factor (%)': dict(threshold=0.013, maxAbsoluteGap=None),
    'Efficiency (%)': dict(threshold=0.012, maxAbsoluteGap=2.5),
}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def statistics(values):
    n = Decimal(len(values))
    mean = sum(values, Decimal(0)) / n
    mse = sum(((x - mean) ** 2 for x in values), Decimal(0)) / n
    relative = mse.sqrt() / abs(mean) if mean else None
    return mean, mse, relative


def select_metric(records, key, threshold=None, max_absolute_gap=None):
    policy = POLICIES.get(key)
    if threshold is None:
        if policy is None:
            raise ValueError(f'No default selection rule for {key}')
        threshold = policy['threshold']
    if max_absolute_gap is None and policy is not None:
        max_absolute_gap = policy['maxAbsoluteGap']
    if not finite(threshold) or not 0 < threshold < 1:
        raise ValueError('Relative RMSE threshold must be between 0 and 1')
    valid = [r for r in records if finite(r.get('meta', {}).get(key))]
    invalid = [r['id'] for r in records if not finite(r.get('meta', {}).get(key))]
    ordered = sorted(valid, key=lambda r: -r['meta'][key])
    selected = []
    best_ids = [r['id'] for r in ordered if r['meta'][key] == ordered[0]['meta'][key]] if ordered else []
    mean = mse = relative = None
    passed = False
    if max_absolute_gap is not None and (not finite(max_absolute_gap) or max_absolute_gap < 0):
        raise ValueError('Maximum absolute gap must be finite and nonnegative')
    with localcontext() as context:
        context.prec = 60
        values = [Decimal(str(r['meta'][key])) for r in ordered]
        limit = Decimal(str(threshold)) ** 2
        for n in range(len(values), 0, -1):
            if n < len(values) and values[n - 1] == values[n]:
                continue
            if max_absolute_gap is not None and values[0] - values[n - 1] > Decimal(str(max_absolute_gap)):
                continue
            mu, error, cv = statistics(values[:n])
            if mu and error / mu ** 2 <= limit:
                selected = ordered[:n]
                mean, mse, relative, passed = mu, error, cv, True
                break
        if not selected and ordered:
            selected = ordered[:len(best_ids)]
            mean, mse, relative = statistics(values[:len(best_ids)])
    ids = [r['id'] for r in selected]
    reasons = {str(r['id']): '未进入最长达标高值前缀' for r in ordered if r['id'] not in ids}
    if max_absolute_gap is not None and ordered:
        reasons.update({str(r['id']): f'与候选最大PCE绝对偏差超过{max_absolute_gap:g}个百分点'
                        for r in ordered if r['id'] not in ids and Decimal(str(ordered[0]['meta'][key])) - Decimal(str(r['meta'][key])) > Decimal(str(max_absolute_gap))})
    reasons.update({str(i): '该指标缺失或不是有限数值' for i in invalid})
    if not ordered:
        status = '无有效数值，无法计算'
    elif not passed:
        status = '未达标：均值为0，相对偏差无法计算'
    elif len(ids) == 1:
        status = '仅1点，无法评价离散性'
    else:
        status = f'相对均方根偏差 ≤ {threshold*100:g}%'
        if max_absolute_gap is not None:
            status += f'，且距候选最大PCE ≤ {max_absolute_gap:g}个百分点'
    return dict(key=key, candidateCount=len(records), validCount=len(valid), count=len(ids),
                selectedIds=ids, bestIds=best_ids, excludedIds=[r['id'] for r in records if r['id'] not in ids],
                excludedReasons=reasons, mean=float(mean) if mean is not None else None,
                mse=float(mse) if mse is not None else None,
                relativeRmse=float(relative) if relative is not None else None,
                threshold=threshold, inclusive=True, maxAbsoluteGapAllowed=max_absolute_gap,
                bestValue=ordered[0]['meta'][key] if ordered else None, passed=passed, status=status)


def condition_scopes(data):
    records = data['uniqueRecords']
    if data.get('conditionScopes'):
        scopes = [dict(label=s['label'], recordIds=s.get('recordIds', s.get('ids', []))) for s in data['conditionScopes']]
    else:
        labels = []
        for r in records:
            for label in ([r['conditionKey']] if r.get('conditionKey') else r.get('resultGroups', [])):
                if label not in labels:
                    labels.append(label)
        if not labels:
            scopes = [dict(label=data.get('conditionLabel') or '本组', recordIds=[r['id'] for r in records])]
        else:
            scopes = [dict(label=label, recordIds=[r['id'] for r in records if r.get('conditionKey') == label or label in r.get('resultGroups', [])]) for label in labels]
    all_ids = {r['id'] for r in records}
    if len({s['label'] for s in scopes}) != len(scopes) or any(not s['label'] for s in scopes):
        raise ValueError('Condition labels must be distinct and nonempty')
    if set(i for s in scopes for i in s['recordIds']) != all_ids:
        raise ValueError('Condition scopes must cover exactly the current unique records')
    if any(len(set(s['recordIds'])) != len(s['recordIds']) for s in scopes):
        raise ValueError('Duplicate record ID inside a condition scope')
    return scopes


def select_all(data):
    records = data['uniqueRecords']
    if len({r['id'] for r in records}) != len(records):
        raise ValueError('Duplicate record IDs in uniqueRecords')
    scopes = condition_scopes(data)
    prepared = []
    for r in records:
        item = dict(r)
        if not item.get('conditionKey'):
            item['conditionKey'] = '|'.join(s['label'] for s in scopes if r['id'] in s['recordIds'])
        prepared.append(item)
    repeated = select_repeated(prepared)
    retained = set(repeated['selectedIds'])
    metrics = {}
    for scope in scopes:
        local = [r for r in records if r['id'] in scope['recordIds']]
        candidates = [r for r in local if r['id'] in retained]
        scope['metricNames'] = {}
        scope['files'] = list(dict.fromkeys(r.get('file') or str(r['id']) for r in local))
        for name, key, unit in METRICS:
            metric_name = f"{scope['label']} {name}" if len(scopes) > 1 else name
            if len(metric_name + '筛选') > 31 or any(ch in metric_name for ch in '[]:*?/' + chr(92)):
                raise ValueError('Condition label is too long or invalid for an Excel sheet name')
            result = dict(select_metric(candidates, key), unit=unit, scopeIds=scope['recordIds'],
                          conditionLabel=scope['label'], sourceFiles=scope['files'], metricName=name)
            result['excludedIds'] = [r['id'] for r in local if r['id'] not in result['selectedIds']]
            result['excludedReasons'].update({str(r['id']): repeated['annotations'][str(r['id'])]['repeatReason'] for r in local if r['id'] not in retained})
            metrics[metric_name] = result
            scope['metricNames'][name] = metric_name
    return dict(method='descending-prefix-inclusive-relative-rmse', policies=POLICIES,
                repeatedTests=repeated, scopes=scopes, metrics=metrics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding='utf-8-sig'))
    result = select_all(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({k: {'n': v['count'], 'mean': v['mean'], 'relativeRmse': v['relativeRmse'], 'status': v['status']}
                      for k, v in result['metrics'].items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
