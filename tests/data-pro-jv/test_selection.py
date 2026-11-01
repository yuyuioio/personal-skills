import importlib.util
import itertools
import math
import random
import sys
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir() else Path(__file__).resolve().parents[2] / 'skills' / 'data-pro-jv'
sys.argv = sys.argv[:1]
sys.path.insert(0, str(ROOT / 'scripts'))
from select_repeated import identity, relative_gap, select_repeated
from select_metrics import select_all, select_metric
PCE, FF = 'Efficiency (%)', 'Fill Factor (%)'


def record(i, pce=10, ff=60, sample='A34', run=None, point='CH1', **extra):
    run = i + 1 if run is None else run
    name = f'{sample}-{run}-O.csv'
    return dict(id=i, file=name, path=f'C:\\fixture\\{name}',
                meta={PCE:pce, FF:ff, 'Name':f'by 7.{point}(1)', 'Area (cm^2)':0.04,
                      'Voc (V)':0.8, 'Jsc (mA/cm^2)':20 + i, 'Rs (ohm)':100+i}, **extra)


def chosen(items):
    return select_repeated(items)['selectedIds']


class RepeatTests(unittest.TestCase):
    def test_pce_first_when_large_gap(self):
        self.assertEqual(chosen([record(0, 10, 40), record(1, 9, 90)]), [0])

    def test_ff_first_when_close(self):
        self.assertEqual(chosen([record(0, 10, 60), record(1, 9.8, 65)]), [1])

    def test_strict_five_percent_boundary(self):
        self.assertEqual(chosen([record(0, 10.5, 60), record(1, 10, 80)]), [0])

    def test_just_below_boundary(self):
        self.assertEqual(chosen([record(0, 10.499999999, 60), record(1, 10, 80)]), [1])

    def test_just_above_boundary(self):
        self.assertEqual(chosen([record(0, 10.500000001, 60), record(1, 10, 80)]), [0])

    def test_no_chain_for_three_runs(self):
        data = [record(0, 10, 60), record(1, 9.6, 65), record(2, 9.2, 80)]
        for permutation in itertools.permutations(data):
            self.assertEqual(chosen(list(permutation)), [1])

    def test_ff_tie_uses_pce(self):
        self.assertEqual(chosen([record(0, 9.8, 65), record(1, 10, 65)]), [1])

    def test_full_tie_keeps_one_in_input_order(self):
        a, b = record(0), record(1)
        self.assertEqual(chosen([a, b]), [0])
        self.assertEqual(chosen([b, a]), [1])

    def test_different_points_can_select_different_runs(self):
        data = [record(0, 10, 60), record(1, 10.5, 60, point='CH2'),
                record(2, 9.8, 65), record(3, 10, 80, point='CH2')]
        self.assertEqual(chosen(data), [1, 2])

    def test_different_samples_not_merged(self):
        self.assertEqual(chosen([record(0), record(1, sample='A35')]), [0, 1])

    def test_area_and_conditions_not_merged(self):
        a, b = record(0), record(1)
        b['meta']['Area (cm^2)'] = 0.1
        self.assertEqual(chosen([a, b]), [0, 1])
        b['meta']['Area (cm^2)'] = 0.04
        b['conditionKey'] = 'different'
        self.assertEqual(chosen([a, b]), [0, 1])

    def test_filename_suffix_and_original_run(self):
        self.assertEqual(identity(record(0))[:3], ('A34-O', '1', 'CH1'))
        a, b = record(0), record(1, 9.8, 70)
        a['file'] = 'A34-O.csv'; a['path'] = 'C:\\fixture\\A34-O.csv'
        self.assertEqual(chosen([a, b]), [1])

    def test_plain_numbered_files(self):
        a, b = record(0), record(1, 9.8, 70)
        for r in [a, b]:
            r['file'] = r['file'].replace('-O', '')
            r['path'] = r['path'].replace('-O', '')
        self.assertEqual(chosen([a, b]), [1])

    def test_channel_renumbered_group_and_measurement_name(self):
        a, b = record(0), record(1, 9.8, 70, point='CH01')
        a['meta']['group'] = 2; b['meta']['group'] = 1
        b['meta']['Name'] = 'new prefix.CH01(7)'
        self.assertEqual(chosen([a, b]), [1])

    def test_unconfirmed_points_not_forced_by_group(self):
        a, b = record(0), record(1)
        for r in [a, b]:
            r['meta']['Name'] = ''; r['meta']['group'] = 1
        self.assertEqual(chosen([a, b]), [0, 1])

    def test_directories_and_explicit_identity(self):
        a, b = record(0), record(1, 9.8, 70)
        b['path'] = b['path'].replace('fixture', 'other')
        self.assertEqual(chosen([a, b]), [0, 1])
        for r in [a, b]:r['sampleId'] = 'same'; r['pointId'] = 'point-1'
        self.assertEqual(chosen([a, b]), [1])

    def test_zero_and_negative_values(self):
        self.assertEqual(chosen([record(0, 0, 60), record(1, 0, 70)]), [1])
        self.assertEqual(chosen([record(0, 0, 90), record(1, 1, 60)]), [1])
        self.assertEqual(chosen([record(0, -1, 60), record(1, -2, 90)]), [0])
        self.assertEqual(chosen([record(0, -1, 60), record(1, -1, 90)]), [1])

    def test_missing_pce_and_ff(self):
        self.assertEqual(chosen([record(0, None), record(1, 9)]), [1])
        out = select_repeated([record(0, None), record(1, None)])
        self.assertEqual(out['selectedIds'], [])
        self.assertIn('无法择优', out['groups'][0]['warning'])
        self.assertEqual(chosen([record(0, 10, None), record(1, 9.8, 70)]), [1])
        self.assertEqual(chosen([record(0, 10, None), record(1, 9.8, None)]), [0])

    def test_single_missing_pce_keeps_other_metrics_available(self):
        r = record(0, None)
        out = select_all({'uniqueRecords':[r]})
        self.assertEqual(out['metrics']['Voc']['selectedIds'], [0])
        self.assertEqual(out['metrics']['PCE']['selectedIds'], [])

    def test_whole_record_and_raw_data_unchanged(self):
        data = [record(0, 10, 60), record(1, 9.8, 70)]
        before = deepcopy(data)
        out = select_all({'uniqueRecords':data})
        self.assertEqual(data, before)
        for metric in out['metrics'].values():
            self.assertEqual(metric['selectedIds'], [1])
            self.assertEqual(metric['candidateCount'], 1)
            self.assertIn('同点选用记录1', metric['excludedReasons']['0'])

    def test_independent_high_prefix_uses_new_inclusive_limit(self):
        values = [dict(id=i, meta={PCE:x}) for i,x in enumerate([101.2,98.8])]
        self.assertEqual(select_metric(values, PCE)['selectedIds'], [0,1])

    def test_random_multirun_against_decimal_oracle(self):
        rng = random.Random(6)
        for _ in range(200):
            data = [record(i, rng.randrange(80, 111)/10, rng.randrange(40,81)) for i in range(rng.randrange(2, 8))]
            rng.shuffle(data)
            maximum = max(Decimal(str(r['meta'][PCE])) for r in data)
            pool = [r for r in data if (maximum-Decimal(str(r['meta'][PCE])))/Decimal(str(r['meta'][PCE])) < Decimal('0.05')]
            best = max(pool, key=lambda r:(r['meta'][FF], r['meta'][PCE]))
            self.assertEqual(chosen(data), [best['id']])


if __name__ == '__main__':
    unittest.main()
