"""Select high-value prefixes independently, retaining every tied maximum."""
import argparse
import json
import math
from decimal import Decimal, localcontext
from pathlib import Path
from select_repeated import select_repeated

METRICS = [('Jsc', 'Jsc (mA/cm^2)', 'mA/cm²'), ('Voc', 'Voc (V)', 'V'),
           ('PCE', 'Efficiency (%)', '%'), ('FF', 'Fill Factor (%)', '%')]


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def statistics(values):
    n = Decimal(len(values))
    mean = sum(values, Decimal(0)) / n
    mse = sum(((x - mean) ** 2 for x in values), Decimal(0)) / n
    relative = mse.sqrt() / abs(mean) if mean else None
    return mean, mse, relative


def select_metric(records, key, threshold=0.05):
    if not finite(threshold) or not 0 < threshold < 1:
        raise ValueError('Relative RMSE threshold must be between 0 and 1')
    valid = [r for r in records if finite(r.get('meta', {}).get(key))]
    invalid = [r['id'] for r in records if not finite(r.get('meta', {}).get(key))]
    ordered = sorted(valid, key=lambda r: -r['meta'][key])
    selected = []
    best_ids = [r['id'] for r in ordered if r['meta'][key] == ordered[0]['meta'][key]] if ordered else []
    mean = mse = relative = None
    passed = False
    with localcontext() as context:
        context.prec = 50
        values = [Decimal(str(r['meta'][key])) for r in ordered]
        limit = Decimal(str(threshold)) ** 2
        for n in range(len(values), 0, -1):
            if n < len(values) and values[n - 1] == values[n]:
                continue
            mu, error, cv = statistics(values[:n])
            if mu and error / mu ** 2 < limit:
                selected = ordered[:n]
                mean, mse, relative, passed = mu, error, cv, True
                break
        if not selected and ordered:
            selected = ordered[:len(best_ids)]
            mean, mse, relative = statistics(values[:len(best_ids)])
    ids = [r['id'] for r in selected]
    reasons = {str(r['id']): '未进入最长达标高值前缀' for r in ordered if r['id'] not in ids}
    reasons.update({str(i): '该指标缺失或不是有限数值' for i in invalid})
    if not ordered:
        status = '无有效数值，无法计算'
    elif not passed:
        status = '未达标：均值为0，相对偏差无法计算'
    elif len(ids) == 1:
        status = '仅1点，无法评价离散性'
    else:
        status = '相对均方根偏差 < 5%'
    return dict(key=key, candidateCount=len(records), validCount=len(valid), count=len(ids),
                selectedIds=ids, bestIds=best_ids, excludedIds=[r['id'] for r in records if r['id'] not in ids],
                excludedReasons=reasons, mean=float(mean) if mean is not None else None,
                mse=float(mse) if mse is not None else None,
                relativeRmse=float(relative) if relative is not None else None,
                threshold=threshold, passed=passed, status=status)


def select_all(data):
    records = data['uniqueRecords']
    if len({r['id'] for r in records}) != len(records):
        raise ValueError('Duplicate record IDs in uniqueRecords')
    repeated = select_repeated(records)
    retained = set(repeated['selectedIds'])
    candidates = [r for r in records if r['id'] in retained]
    metrics = {}
    for name, key, unit in METRICS:
        result = dict(select_metric(candidates, key), unit=unit)
        result['excludedIds'] = [r['id'] for r in records if r['id'] not in result['selectedIds']]
        result['excludedReasons'].update({str(r['id']): repeated['annotations'][str(r['id'])]['repeatReason']
                                         for r in records if r['id'] not in retained})
        metrics[name] = result
    return dict(method='descending-prefix-relative-rmse', threshold=0.05,
                repeatedTests=repeated, metrics=metrics)


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
