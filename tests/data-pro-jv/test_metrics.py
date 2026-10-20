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
        result=module.select_metric(records([105,95]), KEY)
        self.assertEqual(result['selectedIds'],[0])
        self.assertIn('仅1点', result['status'])

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
        data={'uniqueRecords':[{'id':i,'meta':dict(zip([k for _,k,_ in module.METRICS],v))} for i,v in enumerate([(10,1,10,50),(1,1,1,80),(1,1,10,80)])]}
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
                    if error/mu**2<Decimal('0.0025'):eligible.append(n)
            expected=[i for i,_ in ordered[:max(eligible)]]
            self.assertEqual(module.select_metric(records(values),KEY)['selectedIds'],expected)

    def test_nonmonotonic_prefix_dispersion(self):
        # [100,90] fails, but the full four-point prefix passes.
        self.assertEqual(module.select_metric(records([100,90,90,90]),KEY)['count'],4)


if __name__=='__main__':
    unittest.main()
