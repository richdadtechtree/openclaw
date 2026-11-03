/* 책갈피 실제 Chromium 검사. 서버·시세·계정은 모의 데이터 사용. */
const {chromium}=require('playwright');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const html=fs.readFileSync(path.join(__dirname,'../stock/slack_digest_live.html'),'utf8');
const saved=new Map();let failSave=false,photos=true,resetAt=Infinity;
function lifetime(){const now=Date.now()/1000;if(now>=resetAt){saved.clear();resetAt=Infinity;}return {server_now:now,expires_at:Number.isFinite(resetAt)?resetAt:now+3600};}
const srv=http.createServer((req,res)=>{
  const u=new URL(req.url,'http://localhost'),owner=(req.headers.cookie||'').match(/test-user=(\w+)/)?.[1];
  const send=(type,body,code=200)=>{res.writeHead(code,{'Content-Type':type});res.end(body);};
  const json=(b,code=200)=>send('application/json',JSON.stringify(b),code);
  const day=u.searchParams.get('date')||'2026-11-03',edition=u.searchParams.get('edition')||'paper';
  if(u.pathname==='/economy')return send('text/html; charset=utf-8',html);
  if(u.pathname==='/economy/data')return json({date:day,edition,messages:[{
    ts:day+'T06:00:00',source:'user',kind:'text',text:'*[신문요약 1/1] 신문 요약*\n'+
      Array.from({length:15},(_,i)=>(i+1)+'. 기사 제목 '+(i+1)+'\n• WHAT: '+('기사 속 확인 가능한 사실과 숫자를 정리합니다. '.repeat(20))+
      '\n• WHY: 배경과 원인입니다.\n• HOW: 진행 상황을 확인합니다.\n• 사진: 03').join('\n\n')}]});
  if(u.pathname==='/api/news/today')return json({ok:true,ready:true,date:day,count:photos?3:0,images:photos?[1,2,3].map(n=>({
    name:'0'+n+'.jpg',url:'/page.svg',thumb:'/page.svg',download_url:'/page.svg'})):[]});
  if(u.pathname==='/page.svg')return send('image/svg+xml','<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1200"><rect width="800" height="1200" fill="white"/><text x="30" y="200">Paper test</text></svg>');
  if(u.pathname==='/api/news/terms')return json({ok:owner==='a',items:[]},owner==='a'?200:403);
  if(u.pathname==='/api/news/marks')return json({ok:false},403);
  if(u.pathname==='/api/news/bookmark'){
    if(!owner)return json({ok:false},401);
    if(req.method==='GET'){const meta=lifetime();return json({ok:true,bookmark:saved.get(owner)||null,csrf:'csrf-'+owner,...meta});}
    let raw='';req.on('data',c=>raw+=c);req.on('end',()=>{
      if(req.headers['x-csrf-token']!=='csrf-'+owner)return json({ok:false},403);
      if(failSave)return json({ok:false,message:'저장 실패 테스트'},500);
      const b=JSON.parse(raw);if(b.action)return json({ok:false},400);const meta=lifetime();saved.set(owner,b.bookmark);
      json({ok:true,bookmark:saved.get(owner)||null,...meta});
    });return;
  }
  return json({ok:false},404);
});
(async()=>{
  await new Promise(r=>srv.listen(0,'127.0.0.1',r));
  const base='http://127.0.0.1:'+srv.address().port;
  const browser=await chromium.launch({headless:true});let checks=0;
  const check=(ok,label)=>{assert.ok(ok,label);checks++;console.log('OK '+label);};
  const ctx=await browser.newContext({viewport:{width:1280,height:900}});
  await ctx.addCookies([{name:'test-user',value:'a',url:base}]);
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://**/*',r=>r.abort());
  async function ready(){
    await page.waitForFunction(()=>document.querySelectorAll('#feed .brf-art').length===15 && newsState.images.length===3);
    await page.locator('#bm-fab').waitFor({state:'visible'});
  }
  async function openPanel(){
    if(await page.locator('#bm-panel').isHidden())await page.locator('#bm-fab').click();
    await page.waitForFunction(()=>!document.getElementById('bm-save').disabled);
  }
  async function save(mode){await openPanel();if(mode)await page.locator(mode==='page'?'#bm-page':'#bm-summary').check();await page.locator('#bm-save').click();await page.waitForFunction(()=>document.getElementById('bm-status').textContent.includes('저장했어요'));}
  try{
    await page.goto(base+'/economy');await ready();
    const bb=await page.locator('#bm-fab').boundingBox(),tt=await page.locator('#tn-fab').boundingBox();
    check(tt&&Math.abs(bb.y-tt.y)<2&&tt.x>bb.x,'책갈피가 용어 바로 옆');
    await page.evaluate(()=>{document.querySelectorAll('#feed .brf-art')[5].scrollIntoView({behavior:'instant',block:'start'});});
    await save();
    const first=saved.get('a');
    check(first.article.includes('6')&&first.view==='summary','읽던 기사 위치 저장');
    await page.locator('#bm-fab').click();
    await page.locator('#datepick').fill('2026-11-01');await page.locator('#datepick').dispatchEvent('change');
    await page.waitForFunction(()=>state.data.date==='2026-11-01');
    await openPanel();await page.locator('#bm-go').click();await page.locator('#bm-panel').waitFor({state:'hidden'});
    check(await page.evaluate(d=>state.date===d,first.date),'다른 날짜에서 저장 날짜로 이동');
    const near=await page.evaluate(()=>{const r=document.querySelectorAll('#feed .brf-art')[5].getBoundingClientRect();return r.bottom>0&&r.top<innerHeight;});
    check(near,'저장한 기사로 즉시 이동');
    await page.evaluate(()=>{openViewer(2);});
    await page.waitForFunction(()=>document.getElementById('lb-img').naturalWidth>0);
    await save();
    check(saved.get('a').view==='page'&&saved.get('a').page==='03.jpg','크게 보는 지면 저장');
    check(saved.size===1,'계정당 최신 책갈피 한 개');
    await page.reload();await ready();await openPanel();await page.locator('#bm-go').click();
    await page.waitForFunction(()=>!document.getElementById('lb').hidden&&V.i===2);
    check(true,'새로고침 후 같은 지면 열기');
    await save('summary');
    check(saved.get('a').view==='summary'&&saved.get('a').article,'지면에서 요약 책갈피 선택 및 저장');
    await page.locator('#bm-go').click();await page.locator('#bm-panel').waitFor({state:'hidden'});
    check(await page.locator('#lb').isHidden(),'요약 책갈피는 지면을 닫고 요약으로 이동');
    await save('page');
    check(saved.get('a').view==='page'&&saved.get('a').page==='03.jpg','요약에서 연결된 지면 책갈피 선택 및 저장');
    await page.locator('#bm-go').click();await page.waitForFunction(()=>!document.getElementById('lb').hidden&&V.i===2);
    check(true,'선택한 지면 책갈피로 이동');

    await page.evaluate(()=>closeViewer());
    await page.locator('#edtog button[data-ed=online]').click();
    await page.waitForFunction(()=>state.data.edition==='online');
    await page.evaluate(()=>document.querySelectorAll('#feed .brf-art')[7].scrollIntoView({behavior:'instant',block:'start'}));
    await save();
    check(saved.get('a').edition==='online','온라인신문 위치로 최신 책갈피 교체');
    check(await page.locator('#bm-page').isDisabled(),'온라인신문에서는 지면 선택 비활성');
    await page.locator('#bm-fab').click();await page.locator('#edtog button[data-ed=paper]').click();
    await page.waitForFunction(()=>state.data.edition==='paper');
    await openPanel();await page.locator('#bm-go').click();await page.locator('#bm-panel').waitFor({state:'hidden'});
    check(await page.evaluate(()=>state.edition==='online'),'저장한 신문 종류 복원');
    await openPanel();failSave=true;const prev=JSON.stringify(saved.get('a'));
    await page.locator('#bm-save').click();await page.waitForFunction(()=>document.getElementById('bm-status').textContent.includes('저장 실패'));
    check(JSON.stringify(saved.get('a'))===prev,'저장 실패 시 이전 책갈피 유지');failSave=false;
    check(await page.locator('#bm-clear').count()===0,'책갈피 삭제 버튼 제거');
    check(await page.locator('#bm-panel').getByRole('button',{name:/삭제|지우기/}).count()===0,'책갈피에 수동 삭제 메뉴 없음');
    await page.locator('#bm-fab').click();await page.locator('#edtog button[data-ed=paper]').click();
    await page.waitForFunction(()=>state.data.edition==='paper');await page.evaluate(()=>openViewer(2));await save();
    await page.evaluate(()=>closeViewer());await page.locator('#bm-fab').click();photos=false;
    await openPanel();await page.locator('#bm-go').click();
    await page.waitForFunction(()=>document.getElementById('bm-status').textContent.includes('지면이 없어요'));
    check(saved.get('a').page==='03.jpg','원본이 없어도 책갈피 보존 및 안내');photos=true;
    await page.locator('#bm-fab').click();await page.setViewportSize({width:390,height:844});
    await openPanel();
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'모바일 가로 넘침 없음');
    const actions=await page.locator('#reader-actions').boundingBox(),jump=await page.locator('#section-jump').boundingBox();
    check(actions.y>=jump.y+jump.height,'모바일 빠른 이동·책갈피 버튼 겹침 없음');
    await page.keyboard.press('Escape');check(await page.locator('#bm-panel').isHidden(),'Esc는 책갈피만 닫기');
    const other=await browser.newContext({viewport:{width:1280,height:900}});
    await other.addCookies([{name:'test-user',value:'b',url:base}]);
    const p2=await other.newPage();await p2.route('https://**/*',r=>r.abort());
    await p2.goto(base+'/economy');await p2.locator('#bm-fab').waitFor({state:'visible'});await p2.locator('#bm-fab').click();
    await p2.waitForFunction(()=>!document.getElementById('bm-save').disabled);
    check((await p2.locator('#bm-location').textContent()).includes('없어요'),'다른 계정 책갈피 분리');
    check(await p2.locator('#tn-fab').isHidden(),'일반 계정도 용어 권한과 관계없이 책갈피 이용');
    await other.close();
    const realNow=await page.evaluate(()=>Date.now());
    await page.evaluate(()=>{const original=Date.now;Date.now=()=>original()+3*86400000;});
    await openPanel();
    check(!(await page.locator('#bm-go').isDisabled()),'기기 시계가 달라도 서버 만료시간 사용');
    await page.keyboard.press('Escape');
    resetAt=Date.now()/1000+0.8;
    await openPanel();
    await page.waitForFunction(()=>document.getElementById('bm-location').textContent.includes('없어요')&&document.getElementById('bm-go').disabled);
    check(!saved.has('a'),'열어둔 화면도 서버 날짜 변경에 자동 초기화');
    check((await page.locator('#bm-status').textContent()).includes('초기화'),'날짜 변경 초기화 안내');
    check(errors.length===0,'브라우저 오류 없음: '+errors.join('; '));
    console.log('PASS: '+checks+' bookmark browser checks');
  }finally{await ctx.close();await browser.close();await new Promise(r=>srv.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
