/* 관리자 표시 저장/복원, 게스트 수명, 저장 오류·느린 응답을 실제 Chromium에서 검사.
   node scripts/test_viewer_marks.js (필요 시 PW_CHROME=브라우저 실행 파일) */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), assert = require('assert/strict');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || (process.platform === 'win32'
  ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : '/opt/pw-browsers/chromium-1194/chrome-linux/chrome');
const SAVED = new Map();
let admin = true, failSave = false, failLoad = false, loadDelay = 0, saveDelay = 0, posts = 0;
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://localhost');
  const send = (type, body, code = 200) => {res.writeHead(code, {'Content-Type': type});res.end(body);};
  const json = (b, code = 200) => send('application/json', JSON.stringify(b), code);
  const day = u.searchParams.get('date') || '2026-11-03';
  if(u.pathname === '/economy') return send('text/html; charset=utf-8',fs.readFileSync(HTML));
  if(u.pathname === '/away') return send('text/html','<p>Another page</p>');
  if(u.pathname === '/economy/data') return json({date:day,messages:[{ts:day+'T06:29:00',source:'user',kind:'text',text:
    '*[신문요약 1/2] 신문 요약*\n1. 반도체 투자 확대\n• WHAT: 투자가 늘었다.\n• WHY: 수요 증가.\n• HOW: 실적 확인.\n• 사진: 01'}]});
  if(u.pathname === '/api/news/today') return json({ok:true,ready:true,date:day,count:2,images:[1,2].map(n=>({
    name:`0${n}.jpg`,url:'/page.svg',thumb:'/page.svg',download_url:'/page.svg'}))});
  if(u.pathname === '/page.svg') return send('image/svg+xml','<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1200"><rect width="800" height="1200" fill="white"/><text x="50" y="200" font-size="40">Newspaper test</text></svg>');
  if(u.pathname === '/api/news/marks' && req.method === 'GET') return setTimeout(()=>{
    if(!admin) return json({ok:false},403);
    if(failLoad) return json({ok:false},500);
    const pages={}; for(const [k,v] of SAVED) if(k.startsWith(day+'/')) pages[k.slice(11)]=v;
    json({ok:true,pages});
  },loadDelay);
  if(u.pathname === '/api/news/marks' && req.method === 'POST'){
    posts++; let raw='';req.on('data',c=>raw+=c);req.on('end',()=>setTimeout(()=>{
      if(!admin) return json({ok:false},403);
      if(failSave) return json({ok:false,message:'저장 실패 테스트'},500);
      const b=JSON.parse(raw),k=b.date+'/'+b.page, old=SAVED.get(k);
      if((old?.revision||0)!==b.revision) return json({ok:false,message:'다른 창에서 표시가 바뀌었어요'},409);
      SAVED.set(k,{strokes:b.strokes,revision:b.revision+1});json({ok:true,revision:b.revision+1});
    },saveDelay));return;
  }
  if(u.pathname === '/api/news/terms') return json({ok:false},403);
  return json({ok:false},404);
});

(async()=>{
  await new Promise(r=>srv.listen(0,'127.0.0.1',r));
  const base=`http://127.0.0.1:${srv.address().port}`;
  const browser=await chromium.launch({executablePath:CHROME,headless:true});
  const errors=[]; let checks=0;
  const check=(ok,msg)=>{assert.ok(ok,msg);checks++;console.log('OK '+msg);};
  async function context(){
    const ctx=await browser.newContext({viewport:{width:1280,height:900}});
    const p=await ctx.newPage();p.on('pageerror',e=>errors.push(e.message));
    await p.route('https://**/*',route=>route.abort());
    p.on('dialog',d=>d.type()==='confirm'?d.accept():d.dismiss());
    return [ctx,p];
  }
  async function open(p){
    await p.waitForFunction(()=>newsState.images.length>0 && markDay && ['admin','guest','error'].includes(markDay.mode));
    await p.evaluate(()=>{openViewer(0,{pen:true});setHand(false,true);});
    await p.waitForFunction(()=>document.getElementById('lb-img').naturalWidth>0 && V.fitW>0);
  }
  async function line(p,y=.3){
    const r=await p.locator('#lb-img').boundingBox();
    await p.mouse.move(r.x+r.width*.2,r.y+r.height*y);
    await p.mouse.down();await p.mouse.move(r.x+r.width*.6,r.y+r.height*y,{steps:8});await p.mouse.up();
  }
  async function saved(p){await p.waitForFunction(()=>[...MARK_DAYS.values()].every(d=>[...d.jobs.values()].every(j=>!j.dirty&&!j.busy)));}
  let [ctx,p]=await context();
  try{
    await p.goto(base+'/economy');await open(p);await line(p);await saved(p);
    const day=await p.evaluate(()=>M.date),key=day+'/01.jpg';
    check(SAVED.get(key)?.strokes.length===1,'관리자 마우스 줄 긋기 → 서버 저장');
    await p.reload();await open(p);
    check(await p.evaluate(()=>markList().length===1),'새로고침 → 표시 복원');
    await p.evaluate(()=>{closeViewer();openViewer(0,{pen:true});});
    check(await p.evaluate(()=>markList().length===1),'뷰어 닫았다 열기 → 유지');
    await p.evaluate(()=>{go(1);setHand(false,true);});await line(p);await saved(p);
    check(SAVED.get(day+'/02.jpg')?.strokes.length===1,'다른 지면에 별도로 저장');
    await p.evaluate(()=>{closeViewer();state.date='2026-10-01';loadNews();});
    await p.waitForFunction(()=>markDay.date==='2026-10-01'&&markDay.mode==='admin');
    check(await p.evaluate(()=>Object.keys(M.marks).length===0),'날짜별 표시 분리');
    await p.evaluate(d=>{state.date=d;loadNews();},day);await open(p);
    check(await p.evaluate(()=>markList().length===1),'원래 날짜로 돌아오면 복원');
    await p.evaluate(()=>document.getElementById('lb-undo').click());await saved(p);await p.reload();await open(p);
    check(await p.evaluate(()=>markList().length===0),'되돌리기 결과도 새로고침 후 유지');

    await p.evaluate(()=>setTool('oval'));await line(p,.4);await saved(p);
    await p.evaluate(()=>{document.getElementById('lb-c2').click();setWeight(1.7);moveSel(M.sel,M.sel.pts.map(p=>p.slice()),.02,.02);});
    await saved(p);
    check(SAVED.get(key).strokes[0].c==='#4da3ff','동그라미 색 변경 저장');
    check(SAVED.get(key).strokes[0].pts[0][0]>.2,'동그라미 이동 저장');
    await p.evaluate(()=>document.getElementById('lb-clear').click());await saved(p);await p.reload();await open(p);
    check(await p.evaluate(()=>markList().length===0),'모두 지우기 결과 저장');

    saveDelay=250;await line(p);await line(p,.5);await saved(p);saveDelay=0;
    check(SAVED.get(key).strokes.length===2,'느린 저장 중 추가 표시도 순서대로 보관');
    failSave=true;await line(p,.6);
    await p.waitForFunction(()=>document.getElementById('lb-saved').textContent.includes('저장 실패'));
    check(await p.evaluate(()=>markList().length===3),'저장 실패 시 현재 표시는 보존');
    failSave=false;await p.evaluate(()=>flushMarks());await saved(p);
    check(SAVED.get(key).strokes.length===3,'재시도 성공');
    await ctx.close();

    [ctx,p]=await context();await p.goto(base+'/economy');await open(p);
    check(await p.evaluate(()=>markList().length===3),'새 브라우저에서도 관리자 표시 복원');
    SAVED.get(key).revision++;await line(p,.7);
    await p.waitForFunction(()=>document.getElementById('lb-saved').textContent.includes('다른 창'));
    check(SAVED.get(key).strokes.length===3,'다른 창의 저장은 덮어쓰지 않음');
    await ctx.close();

    admin=false;const before=posts;
    [ctx,p]=await context();await p.goto(base+'/economy');await open(p);await line(p);
    check(await p.evaluate(()=>markList().length===1),'게스트도 임시로 줄 긋기 가능');
    check(posts===before,'게스트는 저장 요청 없음');
    await p.evaluate(()=>{closeViewer();openViewer(0,{pen:true});});
    check(await p.evaluate(()=>markList().length===1),'게스트는 같은 페이지에서 뷰어를 다시 열면 유지');
    await p.reload();await open(p);
    check(await p.evaluate(()=>markList().length===0),'게스트 새로고침 시 삭제·관리자 표시 노출 없음');
    await p.evaluate(()=>setHand(false,true));await line(p);
    await p.goto(base+'/away');await p.goBack();await open(p);
    check(await p.evaluate(()=>markList().length===0),'게스트 페이지 이탈 후 뒤로 가기에도 삭제');
    await p.evaluate(()=>setHand(false,true));await line(p);
    await p.evaluate(()=>{dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
    await p.waitForFunction(()=>markDay?.mode==='guest');
    check(await p.evaluate(()=>markList().length===0),'bfcache 복원 시에도 게스트 표시 삭제');
    check(await p.evaluate(()=>!Object.keys(localStorage).some(k=>/mark|stroke/i.test(k))),'브라우저 저장소에 표시를 남기지 않음');
    await ctx.close();

    admin=true;loadDelay=5000;
    [ctx,p]=await context();await p.goto(base+'/economy');
    await p.waitForFunction(()=>newsState.images.length>0);
    await p.evaluate(()=>{openViewer(0,{pen:true});setHand(false,true);});
    check(await p.evaluate(()=>markDay.mode==='loading'),'느린 표시 조회 중');
    await p.waitForFunction(()=>document.getElementById('lb-img').naturalWidth>0 && V.fitW>0);
    await line(p);check(await p.evaluate(()=>markList().length===0),'기존 표시 불러오기 전 편집 차단');
    await p.waitForFunction(()=>markDay.mode==='admin');loadDelay=0;
    check(await p.evaluate(()=>markList().length===3),'불러오기 완료 시 기존 표시 유지');
    await ctx.close();
    failLoad=true;[ctx,p]=await context();await p.goto(base+'/economy');await open(p);
    await p.waitForFunction(()=>markDay.mode==='error');await line(p);
    check(await p.evaluate(()=>markList().length===0),'조회 실패 시 빈 표시로 덮어쓰지 않도록 편집 차단');
    failLoad=false;await p.evaluate(()=>{closeViewer();openViewer(0,{pen:true});});
    await p.waitForFunction(()=>markDay.mode==='admin');
    check(await p.evaluate(()=>markList().length===3),'조회 실패 후 다시 열면 복원 재시도');
    await ctx.close();
    check(errors.length===0,'브라우저 오류 없음: '+errors.join(', '));
    console.log(`${checks} checks passed`);
  }finally{await ctx.close();await browser.close();await new Promise(r=>srv.close(r));}
})().catch(e=>{console.error(e);process.exit(1);});
