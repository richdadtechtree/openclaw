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
    await page.locator('#bm-controls').waitFor({state:'visible'});
    await page.waitForFunction(()=>!document.getElementById('bm-save').disabled);
  }
  async function save(){
    await page.locator('#bm-save').click();
    await page.waitForFunction(()=>document.getElementById('bm-status').textContent==='저장했어요.'&&!document.getElementById('bm-save').disabled);
  }
  async function idle(){await page.waitForFunction(()=>!document.getElementById('bm-go').disabled);}
  try{
    await page.goto(base+'/economy');await ready();
    check(await page.locator('#bm-controls button').count()===2,'책갈피는 저장·불러오기 두 버튼만 표시');
    check(await page.locator('#bm-panel,#bm-kind,#bm-clear,#bm-fab').count()===0,'메뉴·종류 선택·삭제·추가 클릭 제거');
    const bb=await page.locator('#bm-controls').boundingBox(),tt=await page.locator('#tn-fab').boundingBox();
    check(tt&&Math.abs(bb.y-tt.y)<3&&tt.x>bb.x,'용어 옆에 바로 이용하는 버튼 배치');
    await page.locator('#bm-go').click();
    await page.waitForFunction(()=>document.getElementById('bm-status').textContent.includes('저장된 위치가 없어요'));
    check(true,'빈 책갈피 불러오기는 짧게 안내');
    await page.evaluate(()=>document.querySelectorAll('#feed .brf-art')[5].scrollIntoView({behavior:'instant',block:'start'}));
    await save();const first=saved.get('a');
    check(first.article.includes('6')&&first.view==='summary','저장 한 번으로 현재 요약 위치 자동 저장');
    await page.locator('#datepick').fill('2026-11-01');await page.locator('#datepick').dispatchEvent('change');
    await page.waitForFunction(()=>state.data.date==='2026-11-01');
    await page.locator('#bm-go').click();
    await page.waitForFunction(d=>state.date===d&&!document.getElementById('bm-go').disabled,first.date);
    check(await page.evaluate(()=>{const r=document.querySelectorAll('#feed .brf-art')[5].getBoundingClientRect();return r.bottom>0&&r.top<innerHeight;}),'불러오기 한 번으로 저장한 날짜·기사로 이동');
    await page.evaluate(()=>openViewer(2));
    await page.waitForFunction(()=>document.getElementById('lb-img').naturalWidth>0);
    await save();
    check(saved.get('a').view==='page'&&saved.get('a').page==='03.jpg','지면에서 저장을 누르면 종류 선택 없이 지면 저장');
    check(saved.size===1,'최신 위치 한 개만 유지');
    await page.reload();await ready();await page.locator('#bm-go').click();
    await page.waitForFunction(()=>!document.getElementById('lb').hidden&&V.i===2&&!document.getElementById('bm-go').disabled);
    check(true,'불러오기 한 번으로 저장한 지면 열기');
    await page.keyboard.press('Escape');await page.locator('#lb').waitFor({state:'hidden'});
    check(true,'단추에 초점이 있어도 Esc로 지면 닫기');
    failSave=true;const prev=JSON.stringify(saved.get('a'));
    await page.locator('#bm-save').click();
    await page.waitForFunction(()=>document.getElementById('bm-status').textContent.includes('저장 실패'));
    check(JSON.stringify(saved.get('a'))===prev,'저장 실패 시 기존 위치 유지');failSave=false;
    photos=false;await page.locator('#bm-go').click();
    await page.waitForFunction(()=>document.getElementById('bm-status').textContent.includes('지면이 없어요'));
    check(saved.get('a').page==='03.jpg','원본이 없으면 간단한 안내와 기존 저장 유지');photos=true;
    await page.locator('#edtog button[data-ed=online]').click();
    await page.waitForFunction(()=>state.data.edition==='online');
    await page.evaluate(()=>document.querySelectorAll('#feed .brf-art')[7].scrollIntoView({behavior:'instant',block:'start'}));
    await save();check(saved.get('a').edition==='online'&&saved.get('a').view==='summary','온라인신문도 자동 요약 위치 저장');
    await page.locator('#edtog button[data-ed=paper]').click();
    await page.waitForFunction(()=>state.data.edition==='paper');
    await page.locator('#bm-go').click();
    await page.waitForFunction(()=>state.edition==='online'&&!document.getElementById('bm-go').disabled);
    check(true,'신문 종류도 선택 단계 없이 복원');
    await page.setViewportSize({width:390,height:844});
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'모바일 가로 넘침 없음');
    const actions=await page.locator('#reader-actions').boundingBox(),jump=await page.locator('#section-jump').boundingBox();
    check(actions.y>=jump.y+jump.height,'모바일에서 빠른 이동과 두 버튼이 겹치지 않음');
    const other=await browser.newContext({viewport:{width:1280,height:900}});
    await other.addCookies([{name:'test-user',value:'b',url:base}]);
    const p2=await other.newPage();await p2.route('https://**/*',r=>r.abort());
    await p2.goto(base+'/economy');await p2.locator('#bm-controls').waitFor({state:'visible'});
    await p2.waitForFunction(()=>!document.getElementById('bm-go').disabled);
    await p2.locator('#bm-go').click();
    await p2.waitForFunction(()=>document.getElementById('bm-status').textContent.includes('저장된 위치가 없어요'));
    check(!saved.has('b')&&saved.has('a'),'계정별 저장 위치 분리');
    check(await p2.locator('#tn-fab').isHidden(),'일반 계정도 두 버튼으로 이용 가능');
    await other.close();
    resetAt=Date.now()/1000+0.8;
    await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));await idle();
    await page.waitForFunction(()=>document.getElementById('bm-status').textContent.includes('초기화'));await idle();
    check(!saved.has('a'),'열어둔 화면에서도 자정 만료 규칙 유지');
    await page.locator('#bm-go').click();
    await page.waitForFunction(()=>document.getElementById('bm-status').textContent.includes('저장된 위치가 없어요'));
    check(true,'초기화 후 불러오기는 이전 위치로 가지 않음');
    check(errors.length===0,'브라우저 오류 없음: '+errors.join('; '));
    console.log('PASS: '+checks+' simple save/load bookmark browser checks');
  }finally{await ctx.close();await browser.close();await new Promise(r=>srv.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
