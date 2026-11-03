import assert from 'node:assert/strict';
import test from 'node:test';
import {summaryMaximumSpecs,summaryMaximumHeaders} from '../../skills/data-pro-jv/scripts/summary_maxima.mjs';

const keys=['Jsc (mA/cm^2)','Voc (V)','Fill Factor (%)','Efficiency (%)'];
function record(id,values){return {id,meta:Object.fromEntries(keys.map((key,i)=>[key,values[i]]))};}
function table(records){return {sheet:'全部参数',positions:records.map((r,i)=>({id:r.id,row:i+2})),metricFields:keys.map((key,i)=>({key,index:i+1}))};}

test('each maximum uses all retained candidates within its own condition',()=>{
  const records=[record(1,[20,.8,60,10]),record(2,[19,.9,70,9]),record(3,[99,9,99,99]),record(4,[200,2,90,30])];
  const specs=summaryMaximumSpecs({recordIds:[1,2,3]},records,[1,2,4],table(records));
  assert.deepEqual(specs.map(s=>s.expectedValue),[20,.9,70,10]);
  assert.deepEqual(specs.map(s=>s.recordIds),Array.from({length:4},()=>[1,2]));
  assert.deepEqual(summaryMaximumHeaders,['Jsc最大值 (mA/cm²)','Voc最大值 (V)','FF最大值 (%)','PCE最大值 (%)']);
  assert.equal(specs[0].formula,'=IF(COUNT(\'全部参数\'!B2,\'全部参数\'!B3)=0,"无法计算",MAX(\'全部参数\'!B2,\'全部参数\'!B3))');
  const other=summaryMaximumSpecs({recordIds:[4]},records,[1,2,4],table(records));
  assert.deepEqual(other.map(s=>s.expectedValue),[200,2,90,30]);
});

test('blank values do not replace zero or negative maxima',()=>{
  const records=[record(1,[-3,0,null,null]),record(2,[-2,-1,null,null]),record(3,[null,null,null,null])];
  const specs=summaryMaximumSpecs({recordIds:[1,2,3]},records,[1,2,3],table(records));
  assert.deepEqual(specs.map(s=>s.expectedValue),[-2,0,'无法计算','无法计算']);
  // Keep the blank candidate cell in the live formula so a later numeric edit participates.
  assert.equal(specs[0].formula,'=IF(COUNT(\'全部参数\'!B2,\'全部参数\'!B3,\'全部参数\'!B4)=0,"无法计算",MAX(\'全部参数\'!B2,\'全部参数\'!B3,\'全部参数\'!B4))');
});

test('no retained candidates displays an explicit unavailable value',()=>{
  const records=[record(1,[20,.8,60,10])];
  const specs=summaryMaximumSpecs({recordIds:[1]},records,[],table(records));
  assert.deepEqual(specs.map(s=>s.expectedValue),Array(4).fill('无法计算'));
  assert.deepEqual(specs.map(s=>s.formula),Array(4).fill('="无法计算"'));
});
