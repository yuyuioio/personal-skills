import importlib.util
import itertools
import json
import random
import subprocess
import sys
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv)>1 and Path(sys.argv[1]).is_dir() else Path(__file__).resolve().parents[2]/'skills'/'data-pro-jv'
sys.argv = sys.argv[:1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'scripts'))
spec = importlib.util.spec_from_file_location('select_metrics', ROOT/'scripts/select_metrics.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
KEY = 'Efficiency (%)'


def records(values):
    return [dict(id=i, meta={KEY:x}) for i,x in enumerate(values)]


class SelectionTests(unittest.TestCase):
    def test_exact_boundary(self):
        result=module.select_metric(records([101.2,98.8]), KEY)
        self.assertEqual(result['selectedIds'],[0,1])
        self.assertAlmostEqual(result['relativeRmse'],0.012)
        self.assertEqual(module.select_metric(records([101.2,98.799]),KEY)['selectedIds'],[0])

    def test_metric_specific_inclusive_boundaries(self):
        for key,upper in [('Jsc (mA/cm^2)',0.008),('Voc (V)',0.008),('Fill Factor (%)',0.013)]:
            values=[100+100*upper,100-100*upper]
            data=[dict(id=i,meta={key:v}) for i,v in enumerate(values)]
            self.assertEqual(module.select_metric(data,key)['count'],2)
            data[1]['meta'][key]-=0.001
            self.assertEqual(module.select_metric(data,key)['count'],1)

    def test_pce_absolute_gap_and_joint_conditions(self):
        self.assertEqual(module.select_metric(records([200,197.5]),KEY)['count'],2)
        out=module.select_metric(records([200,197.499]),KEY)
        self.assertEqual(out['selectedIds'],[0])
        self.assertIn('2.5个百分点',out['excludedReasons']['1'])
        self.assertEqual(module.select_metric(records([10,7.5]),KEY)['count'],1)

    def test_best_ties_and_provenance(self):
        result=module.select_metric(records([20,100,99,100]),KEY)
        self.assertEqual(result['selectedIds'],[1,3,2])
        self.assertEqual(result['bestIds'],[1,3])
        self.assertAlmostEqual(result['mean'],299/3)

    def test_zero_missing_negative(self):
        self.assertFalse(module.select_metric(records([0,0]),KEY)['passed'])
        self.assertIsNone(module.select_metric(records([0,0]),KEY)['relativeRmse'])
        self.assertEqual(module.select_metric(records([None,float('nan')]),KEY)['count'],0)
        self.assertEqual(module.select_metric(records([-1,-1,-1]),KEY)['count'],3)
        self.assertEqual(module.select_metric(records([10,10,10]),KEY)['count'],3)

    def test_independent_metrics(self):
        keys=['Jsc (mA/cm^2)','Voc (V)','Efficiency (%)','Fill Factor (%)']
        data={'uniqueRecords':[{'id':i,'meta':dict(zip(keys,v))} for i,v in enumerate([(10,1,10,50),(1,1,1,80),(1,1,10,80)])]}
        out=module.select_all(data)['metrics']
        self.assertEqual(out['Jsc']['selectedIds'],[0])
        self.assertEqual(out['Voc']['count'],3)
        self.assertEqual(out['PCE']['selectedIds'],[0,2])
        self.assertEqual(out['FF']['selectedIds'],[1,2])

    def test_longest_prefix_against_decimal_oracle(self):
        rng=random.Random(42)
        for _ in range(250):
            values=[rng.randrange(85,106) for _ in range(rng.randrange(2,15))]
            ordered=sorted(enumerate(values),key=lambda p:-p[1])
            eligible=[]
            for n in range(1,len(ordered)+1):
                if n<len(ordered) and ordered[n-1][1]==ordered[n][1]:continue
                with localcontext() as ctx:
                    ctx.prec=50
                    xs=[Decimal(x) for _,x in ordered[:n]]
                    mu=sum(xs)/n
                    error=sum((x-mu)**2 for x in xs)/n
                    if error/mu**2<=Decimal('0.012')**2 and xs[0]-xs[-1]<=Decimal('2.5'):eligible.append(n)
            expected=[i for i,_ in ordered[:max(eligible)]]
            self.assertEqual(module.select_metric(records(values),KEY)['selectedIds'],expected)

    def test_nonmonotonic_prefix_dispersion(self):
        # [100,97.6] exceeds 1.2% CV, but all four pass CV and the 2.5-point gap.
        self.assertEqual(module.select_metric(records([100,97.6,97.6,97.6]),KEY)['count'],4)

    def test_explicit_conditions_keep_same_named_samples_separate(self):
        data=[dict(id=i,file='A1-1.csv',path='C:/input/A1-1.csv',conditionKey=None,
                   meta={KEY:10+i,'Fill Factor (%)':60,'Jsc (mA/cm^2)':20,'Voc (V)':1,'Name':'CH1','Area (cm^2)':.09}) for i in range(2)]
        out=module.select_all(dict(uniqueRecords=data,conditionScopes=[dict(label='条件A',ids=[0]),dict(label='条件B',ids=[1])]))
        self.assertEqual(out['repeatedTests']['selectedIds'],[0,1])
        self.assertEqual(len(out['metrics']),8)

    def test_all_tied_maxima_always_survive(self):
        for name,key,unit in module.METRICS:
            data=[dict(id=i,meta={key:x}) for i,x in enumerate([20,10,20,19.99])]
            out=module.select_metric(data,key)
            self.assertEqual(out['bestIds'],[0,2])
            self.assertTrue({0,2}.issubset(out['selectedIds']))


if __name__=='__main__':
    unittest.main()
