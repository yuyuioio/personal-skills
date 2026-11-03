const metrics = [
  ['Jsc', 'Jsc (mA/cm^2)', 'Jsc最大值 (mA/cm²)'],
  ['Voc', 'Voc (V)', 'Voc最大值 (V)'],
  ['FF', 'Fill Factor (%)', 'FF最大值 (%)'],
  ['PCE', 'Efficiency (%)', 'PCE最大值 (%)'],
];

function column(n) {
  let result = '';
  for (; n; n = Math.floor((n - 1) / 26)) result = String.fromCharCode(65 + (n - 1) % 26) + result;
  return result;
}

export const summaryMaximumHeaders = metrics.map(([, , label]) => label);

export function summaryMaximumSpecs(scope, records, retainedIds, allTable) {
  const scopeIds = new Set(scope.recordIds);
  const retained = new Set(retainedIds);
  const candidates = records.filter(record => scopeIds.has(record.id) && retained.has(record.id));
  const positions = new Map(allTable.positions.map(position => [position.id, position.row]));
  const sheet = allTable.sheet.replaceAll("'", "''");
  return metrics.map(([metric, key, label]) => {
    const field = allTable.metricFields.find(item => item.key === key);
    if (!field) throw new Error(`Missing maximum source field: ${key}`);
    const refs = candidates.map(record => {
      if (!positions.has(record.id)) throw new Error(`Missing maximum source row: ${record.id}`);
      return `'${sheet}'!${column(field.index + 1)}${positions.get(record.id)}`;
    });
    const values = candidates.map(record => record.meta[key]).filter(value => typeof value === 'number' && Number.isFinite(value));
    const args = refs.join(',');
    return {
      metric, key, label, recordIds: candidates.map(record => record.id),
      formula: refs.length ? `=IF(COUNT(${args})=0,"无法计算",MAX(${args}))` : '="无法计算"',
      expectedValue: values.length ? Math.max(...values) : '无法计算',
    };
  });
}
