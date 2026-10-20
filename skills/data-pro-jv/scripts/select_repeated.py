"""Choose one complete measurement per sample/point before metric filtering."""
import math
import re
from collections import defaultdict
from decimal import Decimal, localcontext
from pathlib import PureWindowsPath

PCE = 'Efficiency (%)'
FF = 'Fill Factor (%)'


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def identity(record):
    """Numbered terminal runs share a sample; a trailing export tag stays part of it."""
    source = PureWindowsPath(record.get('path') or record.get('file') or str(record['id']))
    stem = PureWindowsPath(record.get('file') or source.name).stem
    match = re.fullmatch(r'(.+)-(\d+)((?:-[A-Za-z]+)?)', stem)
    sample = record.get('sampleId') or (match[1] + match[3] if match else stem)
    run = record.get('measurementGroup') or (match[2] if match else stem)
    name = str(record.get('meta', {}).get('Name') or '')
    channel = re.search(r'\bCH\s*(\d+)\b', name, re.IGNORECASE)
    point = record.get('pointId') or (f'CH{int(channel[1])}' if channel else name)
    # A group index is not a stable point identity when channels are missing/reordered.
    if not point:
        point = f"未确认点位/记录{record['id']}"
    condition = tuple(str(record.get(k, '')) for k in ('conditionKey', 'conditionId', 'conditionLabel', 'scanDirection'))
    meta = record.get('meta', {})
    area = meta.get('Area (cm^2)')
    condition += (str(area), str(meta.get('Scan direction', '')), str(meta.get('Light intensity (mW/cm^2)', '')))
    # Separate directories unless the caller explicitly identifies the same sample.
    scope = '' if record.get('sampleId') else str(source.parent).casefold()
    return sample, str(run), str(point), (scope, str(sample), str(point), condition)


def relative_gap(a, b):
    if a == b:
        return Decimal(0)
    if min(a, b) <= 0:
        return None
    return abs(a - b) / min(a, b)


def select_repeated(records):
    groups = defaultdict(list)
    annotations = {}
    for record in records:
        sample, run, point, key = identity(record)
        groups[key].append(record)
        annotations[str(record['id'])] = dict(sampleId=sample, measurementGroup=run, pointId=point)
    selected = set()
    comparisons = []
    with localcontext() as context:
        context.prec = 50
        for items in groups.values():
            valid = [r for r in items if finite(r.get('meta', {}).get(PCE))]
            gaps = {}
            eligible = []
            winner = None
            warning = ''
            if len(items) == 1:
                winner = items[0]  # A single original record remains available to other metrics.
                eligible = items[:]
                reason = '唯一测试记录'
            elif valid:
                best = max(Decimal(str(r['meta'][PCE])) for r in valid)
                for record in valid:
                    gap = relative_gap(best, Decimal(str(record['meta'][PCE])))
                    gaps[record['id']] = float(gap) if gap is not None else None
                    if gap is not None and gap < Decimal('0.05'):
                        eligible.append(record)
                with_ff = [r for r in eligible if finite(r['meta'].get(FF))]
                pool = with_ff or eligible
                # Input order is only a final tie-breaker, after FF and PCE.
                winner = max(pool, key=lambda r: (
                    Decimal(str(r['meta'][FF])) if with_ff else Decimal(0),
                    Decimal(str(r['meta'][PCE]))))
                reason = '最高PCE' if len(eligible) == 1 else '与最高PCE相对差<5%，FF优先；FF并列取PCE高者，仍并列取输入首条'
                if len(with_ff) < len(eligible):
                    warning = '部分近优候选FF缺失；按有效FF比较，无有效FF时按PCE择优'
                if len(valid) < len(items):
                    warning += ('；' if warning else '') + '部分重复记录PCE缺失或无效，未参加择优'
            else:
                reason = '所有重复记录PCE缺失或无效，无法择优'
                warning = reason
            if winner is not None:
                selected.add(winner['id'])
            for record in items:
                chosen = winner is not None and record['id'] == winner['id']
                annotations[str(record['id'])].update(
                    retentionStatus='保留' if chosen else '未选用（原始记录保留）',
                    repeatSelected=chosen, repeatWinnerId=winner['id'] if winner else None,
                    repeatReason=(reason if chosen else f"同点选用记录{winner['id']}：{reason}" if winner else reason),
                    repeatWarning=warning)
            comparisons.append(dict(
                sampleId=annotations[str(items[0]['id'])]['sampleId'],
                pointId=annotations[str(items[0]['id'])]['pointId'],
                recordIds=[r['id'] for r in items], selectedId=winner['id'] if winner else None,
                eligibleIds=[r['id'] for r in eligible], relativeGaps={str(k): v for k, v in gaps.items()},
                reason=reason, warning=warning))
    return dict(method='pointwise-pce-then-ff', threshold=0.05,
                selectedIds=[r['id'] for r in records if r['id'] in selected],
                excludedIds=[r['id'] for r in records if r['id'] not in selected],
                annotations=annotations, groups=comparisons,
                repeatedPointCount=sum(len(g['recordIds']) > 1 for g in comparisons))
