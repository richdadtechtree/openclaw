/* CHECK annotation -> summary article status: real Chromium, isolated mock server. */
const {chromium}=require('playwright');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const html=fs.readFileSync(path.join(__dirname,'../stock/slack_digest_live.html'),'utf8');
const stored=new Map();let admin=true,posts=0,checks=0;
const titles=['1. 알파 주택 시장','2. 베타 반도체 수출','3. 감마 에너지 가격','4. 델타 금융 정책','5. 엡실론 고용 지표','6. 연결 없는 기사'];
const pages=[1,1,2,2,3,0];
const server=http.createServer((req,res)=>{
  const u=new URL(req.url,'http://localhost'),day=u.searchParams.get('date')||'2026-11-04';
  const send=(type,body,code=200)=>{res.writeHead(code,{'Content-Type':type});res.end(body);};
  const json=(value,code=200)=>send('application/json',JSON.stringify(value),code);
  if(u.pathname==='/economy')return send('text/html; charset=utf-8',html);
  if(u.pathname==='/economy/data'){
    const text='[신문요약 1/1] '+day+'\n\n'+titles.map((t,i)=>t+'\n• WHAT: 사실을 확인합니다.\n• WHY: 원인을 봅니다.\n• HOW: 경과를 봅니다.'+(pages[i]?'\n• 사진: '+pages[i]:'')).join('\n\n')+
      '\n\n'+JSON.stringify({date:day,articles:[{title:titles[2],page:2,bbox:[0,0,.5,1]},{title:titles[3],page:2,bbox:[.5,0,.5,1]}]});
    return json({date:day,messages:[{ts:day+'T06:00:00+09:00',kind:'text',source:'user',text}]});
  }
  if(u.pathname==='/api/news/today')return json({ok:true,ready:true,date:day,count:3,images:[1,2,3].map(n=>({
    name:'0'+n+'.jpg',url:'/page.svg',thumb:'/page.svg',download_url:'/page.svg'}))});
  if(u.pathname==='/page.svg')return send('image/svg+xml','<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1800"><rect width="1200" height="1800" fill="white"/></svg>');
  if(u.pathname==='/api/news/marks'){
    if(!admin)return json({ok:false},403);
    if(req.method==='GET'){
      const result={};for(const[k,v]of stored)if(k.startsWith(day+'/'))result[k.slice(11)]=v;
      return json({ok:true,pages:result});
    }
    posts++;let raw='';req.on('data',c=>raw+=c);req.on('end',()=>{
      const b=JSON.parse(raw),key=b.date+'/'+b.page,old=stored.get(key);
      if((old?.revision||0)!==b.revision)return json({ok:false},409);
      stored.set(key,{strokes:b.strokes,revision:b.revision+1});json({ok:true,revision:b.revision+1});
    });return;
  }
  return json({ok:false},403);
});
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser=await chromium.launch({headless:true}),base='http://127.0.0.1:'+server.address().port;
  const errors=[];
  let ctx=await browser.newContext({viewport:{width:1280,height:900}}),page;
  const check=(v,label)=>{assert.ok(v,label);checks++;console.log('OK '+label);};
  async function newPage(){
    await ctx.route('https://**/*',r=>r.abort());page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
  }
  async function ready(){
    await page.waitForFunction(()=>document.querySelectorAll('#feed .brf-art').length===6&&document.querySelectorAll('#feed .brf-side[data-i]').length===5&&markDay&&['admin','guest'].includes(markDay.mode));
  }
  async function open(index,article=null){
    await page.evaluate(({index,article})=>openViewer(index,article===null?{}:{art:document.querySelectorAll('#feed .brf-art')[article]}),{index,article});
    await page.waitForFunction(()=>document.getElementById('lb-img').naturalWidth>0&&V.loadedTok===V.loadTok&&V.fitW>0);
    await page.waitForFunction(()=>{const r=document.getElementById('lb-img').getBoundingClientRect();return Math.abs(r.width-V.fitW*V.zoom)<1&&Math.abs(r.height-V.fitH*V.zoom)<1;});
  }
  async function stamp(x=.25,y=.3,key='4'){
    const r=await page.locator('#lb-img').boundingBox();
    await page.mouse.move(r.x+r.width*x,r.y+r.height*y);await page.keyboard.press(key);
  }
  const badges=()=>page.evaluate(()=>[...document.querySelectorAll('#feed .brf-art')].map(a=>a.querySelector('.brf-check')?.dataset.check||''));
  const marks=()=>page.evaluate(()=>JSON.parse(JSON.stringify(markList())));
  async function saved(){await page.waitForFunction(()=>[...MARK_DAYS.values()].every(d=>[...d.jobs.values()].every(j=>!j.dirty&&!j.busy)));}
  async function close(){await page.evaluate(()=>closeViewer());await saved();}
  async function erase(st){
    await page.keyboard.press('Delete');
    await page.waitForFunction(()=>{const r=document.getElementById('lb-img').getBoundingClientRect();return Math.abs(r.width-V.fitW*V.zoom)<1&&Math.abs(r.height-V.fitH*V.zoom)<1;});
    const r=await page.locator('#lb-img').boundingBox();
    await page.mouse.click(r.x+(st.pts[0][0]+st.pts[1][0])/2*r.width,r.y+(st.pts[0][1]+st.pts[1][1])/2*r.height);
    await saved();
  }
  try{
    await newPage();await page.goto(base+'/economy');await ready();
    const day=await page.evaluate(()=>state.date),keys=await page.evaluate(()=>[...document.querySelectorAll('#feed .brf-art')].map(a=>artKey(artTitle(a))));
    assert.deepEqual(await badges(),['','','','','','']);check(true,'no badge before CHECK');
    await open(0,0);await stamp();await saved();
    assert.deepEqual(await badges(),['article','','','','','']);check(true,'CHECK identifies the opened article without checking another article on the same page');
    check((await marks()).at(-1).article===keys[0],'CHECK stores its article identity');
    check(await page.locator('#lb-note .nt-art').first().locator('.brf-check').textContent()==='✓ CHECK','viewer summary updates immediately');
    await close();await open(0,1);await stamp(.6,.6,'1');
    assert.deepEqual(await badges(),['article','','','','','']);check(true,'WHAT does not check an article');
    await stamp(.6,.6);await saved();
    assert.deepEqual(await badges(),['article','article','','','','']);check(true,'each article has its own CHECK status');
    let beta=(await marks()).at(-1),r=await page.locator('#lb-img').boundingBox();
    await page.mouse.move(r.x+(beta.pts[0][0]+beta.pts[1][0])/2*r.width,r.y+(beta.pts[0][1]+beta.pts[1][1])/2*r.height);
    await page.mouse.down();await page.mouse.move(r.x+r.width*.7,r.y+r.height*.65,{steps:5});await page.mouse.up();
    check((await marks()).at(-1).article===keys[1],'moving an unboxed article CHECK keeps the article association');
    beta=(await marks()).at(-1);await erase(beta);
    assert.deepEqual(await badges(),['article','','','','','']);check(true,'Delete eraser removes only the affected summary badge');
    await close();await open(0,0);await stamp(.4,.4);await saved();
    await page.keyboard.press('Control+z');await saved();
    assert.deepEqual(await badges(),['article','','','','','']);check(true,'removing one of two CHECK stamps keeps the article checked');
    await close();await page.reload();await ready();
    assert.deepEqual(await badges(),['article','','','','','']);check(true,'summary badges restore before opening a viewer');
    await page.evaluate(()=>{lastSnapshot=null;render();});
    assert.deepEqual(await badges(),['article','','','','','']);check(true,'summary rerender restores CHECK without duplicate badges');
    assert.deepEqual(await page.evaluate(()=>[...document.querySelectorAll('#feed .brf-art')].map(a=>artKey(artTitle(a)))),keys);
    check(true,'CHECK badge does not change article titles, links or bookmark identity');
    await page.evaluate(()=>{state.date='2026-10-01';load();loadNews();});
    await page.waitForFunction(()=>M.date==='2026-10-01'&&newsState.date===state.date&&state.data.date===state.date&&markDay.mode==='admin');
    assert.deepEqual(await badges(),['','','','','','']);check(true,'CHECK status is isolated by date');
    await page.evaluate(day=>{state.date=day;load();loadNews();},day);
    await page.waitForFunction(day=>M.date===day&&newsState.date===day&&state.data.date===day&&markDay.mode==='admin',day);
    await open(1);await stamp(.2,.3);await saved();
    assert.deepEqual(await badges(),['article','','article','','','']);check(true,'full-page CHECK uses article bounding boxes');
    const gamma=(await marks()).at(-1);r=await page.locator('#lb-img').boundingBox();
    await page.mouse.move(r.x+(gamma.pts[0][0]+gamma.pts[1][0])/2*r.width,r.y+(gamma.pts[0][1]+gamma.pts[1][1])/2*r.height);
    await page.mouse.down();await page.mouse.move(r.x+r.width*.8,r.y+r.height*.3,{steps:6});await page.mouse.up();await saved();
    assert.deepEqual(await badges(),['article','','','article','','']);check(true,'dragging CHECK into another article updates both badges');
    check((await marks()).at(-1).article===keys[3],'moved CHECK saves its new article identity');
    await close();await page.reload();await ready();
    assert.deepEqual(await badges(),['article','','','article','','']);check(true,'bounding-box article check survives reload');
    await open(1);await erase((await marks()).find(s=>s.label==='CHECK'));
    assert.deepEqual(await badges(),['article','','','','','']);check(true,'erasing the last CHECK clears its article status');
    await close();await open(0);await stamp(.8,.2);await saved();
    check(!(await marks()).at(-1).article,'ambiguous full-page CHECK does not invent an article association');
    assert.deepEqual(await badges(),['article','page','','','','']);check(true,'unknown location is clearly labeled page CHECK instead of marking every article checked');
    await erase((await marks()).at(-1));await close();
    stored.set(day+'/03.jpg',{revision:1,strokes:[{t:'sticker',label:'CHECK',c:'#b45309',w:.01,pts:[[.2,.2],[.4,.25]]}]});
    await page.reload();await ready();
    assert.deepEqual(await badges(),['article','','','','article','']);check(true,'older CHECK stamps work for a uniquely linked article');
    await page.evaluate(()=>{state.edition='online';lastDecor=null;decorate(true);});
    check(await page.locator('#feed .brf-check').count()===0,'online edition never inherits newspaper CHECK badges');
    await ctx.close();admin=false;ctx=await browser.newContext({viewport:{width:390,height:844}});await newPage();
    await page.goto(base+'/economy');await ready();const previousPosts=posts;
    await open(0,1);await stamp(.5,.5);await close();
    assert.deepEqual(await badges(),['','article','','','','']);check(true,'guest CHECK updates the summary on a narrow screen');
    check(posts===previousPosts,'guest checks retain temporary annotation storage');
    await page.reload();await ready();
    check(await page.locator('#feed .brf-check').count()===0,'temporary guest CHECK clears on reload');
    check(errors.length===0,'no browser errors: '+errors.join(';'));
    console.log('PASS: '+checks+' summary CHECK browser checks');
  }finally{await ctx.close();await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
