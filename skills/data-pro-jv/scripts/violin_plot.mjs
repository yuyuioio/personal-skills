function quantile(sorted, fraction) {
  const position = (sorted.length - 1) * fraction;
  const index = Math.floor(position);
  return sorted[index] + (position - index) * (sorted[Math.ceil(position)] - sorted[index]);
}

function filledBand(grid) {
  // Adjacent horizontal strokes fill the band using data-bound Excel series.
  return grid.flatMap(([y,left,right],i) => i % 2 === 0 ? [[left,y],[right,y]] : [[right,y],[left,y]]);
}

function coordinates(kind, name, vertices) {
  return {kind,name,x:vertices.map(point=>point[0]),y:vertices.map(point=>point[1])};
}

function displayAxis(low, high, clampAtZero) {
  const width=high-low;
  const target=width/5;
  const base=10**Math.floor(Math.log10(target));
  const step=([1,2,2.5,5,10].find(m=>m*base>=target) ?? 10)*base;
  const min=Math.floor((low-width*.03)/step)*step;
  return {min:clampAtZero?Math.max(0,min):min,max:Math.ceil((high+width*.03)/step)*step,step};
}

export function violinPlot(values) {
  const sorted=[...values].sort((a,b)=>a-b);
  const n=values.length, low=sorted[0], high=sorted.at(-1);
  const nonnegative=low>=0;
  const padding=Math.max(Math.abs(low)*.009,.002);
  if (n===1) return {type:'single',axis:displayAxis(low-padding,high+padding,nonnegative),lines:[],pointX:[1]};
  if (low===high) {
    const line=coordinates('box','中位数',[[.91,low],[1.09,low]]);
    const pointX=values.map((_,i)=>1+(i%2===0?-1:1)*(.102+.018*(Math.floor(i/2)%12)));
    return {type:'constant',axis:displayAxis(low-padding,high+padding,nonnegative),lines:[line],pointX};
  }
  const q1=quantile(sorted,.25), median=quantile(sorted,.5), q3=quantile(sorted,.75);
  const iqr=q3-q1;
  const within=sorted.filter(y=>y>=q1-1.5*iqr&&y<=q3+1.5*iqr);
  const whiskerLow=within[0],whiskerHigh=within.at(-1);
  const mean=values.reduce((sum,y)=>sum+y,0)/n;
  const sd=Math.sqrt(values.reduce((sum,y)=>sum+(y-mean)**2,0)/(n-1));
  const band=.9*Math.min(sd,iqr>0?iqr/1.34:sd)*n**(-.2);
  const from=nonnegative?Math.max(0,low-3.5*band):low-3.5*band, to=high+3.5*band;
  function density(y) {
    return values.reduce((sum,x)=>sum+Math.exp(-.5*((y-x)/band)**2)
      +(nonnegative?Math.exp(-.5*((y+x)/band)**2):0),0);
  }
  const sample=Array.from({length:241},(_,i)=>{
    const y=from+(to-from)*i/240;
    return [y,density(y)];
  });
  const peak=Math.max(...sample.map(row=>row[1]));
  const width=d=>.32*d/peak;
  const grid=sample.map(([y,d])=>[y,1-width(d),1+width(d)]);
  const contour=[...grid.map(([y,left])=>[left,y]),...grid.toReversed().map(([y,,right])=>[right,y])];
  contour.push(contour[0]);
  const lines=[coordinates('densityFill','核密度填色',filledBand(grid)),
    coordinates('density','核密度轮廓',contour)];
  const l=.95,r=1.05;
  if (q3>q1) {
    const interior=Array.from({length:151},(_,i)=>[q1+(q3-q1)*i/150,l,r]);
    lines.push(coordinates('boxFill','四分位箱底色',filledBand(interior)));
  }
  const box=[[.978,whiskerLow],[1.022,whiskerLow],[1,whiskerLow],[1,q1],[l,q1],
    [l,median],[r,median],[r,q1],[l,q1],[l,q3],[r,q3],[r,median],[r,q3],
    [1,q3],[1,whiskerHigh],[.978,whiskerHigh],[1.022,whiskerHigh]];
  lines.push(coordinates('box','箱线与中位数',box));
  const occupied=[];
  const pointX=values.map((y,i)=>{
    const room=Math.max(.12,Math.min(.25,width(density(y))*.85));
    const direction=i%2===0?-1:1;
    const preferred=.067+(room-.067)*((i*.618033988749895)%1);
    const steps=Array.from({length:16},(_,k)=>.067+(room-.067)*k/15);
    const choices=[...steps.map(x=>direction*x),...steps.map(x=>-direction*x)]
      .sort((a,b)=>Math.abs(a-direction*preferred)-Math.abs(b-direction*preferred));
    const offset=choices.find(x=>occupied.every(p=>Math.hypot((x-p.x)/.02,(y-p.y)/((to-from)*.022))>=1))
      ?? direction*preferred;
    occupied.push({x:offset,y});
    return 1+offset;
  });
  return {type:'violin',axis:displayAxis(from,to,nonnegative),lines,pointX,
    box:{q1,median,q3,whiskerLow,whiskerHigh,band}};
}
