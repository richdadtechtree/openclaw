/* WHAT/WHY/HOW stickers: real Chromium, mock price-free newspaper server. */
const {chromium}=require('playwright');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const html=fs.readFileSync(path.join(__dirname,'../stock/slack_digest_live.html'),'utf8');
const stored=new Map();let admin=true,posts=0,checks=0;
const server=http.createServer((req,res)=>{
  const u=new URL(req.url,'http://localhost'),day=u.searchParams.get('date')||'2026-11-03';
  const send=(type,body,code=200)=>{res.writeHead(code,{'Content-Type':type});res.end(body);};
  const json=(value,code=200)=>send('application/json',JSON.stringify(value),code);
  if(u.pathname==='/economy')return send('text/html; charset=utf-8',html);
  if(u.pathname==='/economy/data')return json({date:day,messages:[{ts:day+'T06:00:00+09:00',kind:'text',source:'user',
    text:'[신문요약 1/1] '+day+'\n\n1. 테스트 신문 기사\n• WHAT: 사실을 확인합니다.\n• WHY: 원인을 확인합니다.\n• HOW: 경과를 봅니다.\n• 사진: 01'}]});
  if(u.pathname==='/api/news/today')return json({ok:true,ready:true,date:day,count:2,images:[1,2].map(n=>({
    name:'0'+n+'.jpg',url:'/page.svg',thumb:'/page.svg',download_url:'/page.svg'}))});
  if(u.pathname==='/page.svg')return send('image/svg+xml','<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1800"><rect width="1200" height="1800" fill="white"/></svg>');
  if(u.pathname==='/api/news/marks'){
    if(!admin)return json({ok:false},403);
    if(req.method==='GET'){
      const pages={};for(const[key,value]of stored)if(key.startsWith(day+'/'))pages[key.slice(11)]=value;
      return json({ok:true,pages});
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
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base='http://127.0.0.1:'+server.address().port,browser=await chromium.launch({headless:true});
  const check=(value,label)=>{assert.ok(value,label);checks++;console.log('OK '+label);};
  const errors=[];
  async function context(viewport={width:1280,height:900}){
    const ctx=await browser.newContext({viewport});await ctx.route('https://**/*',r=>r.abort());
    const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));return [ctx,page];
  }
  async function open(page,pen=false){
    await page.waitForFunction(()=>newsState.images.length===2&&markDay&&['admin','guest'].includes(markDay.mode));
    await page.evaluate(pen=>{openViewer(0,{pen});if(pen)setHand(false,true);},pen);
    await page.waitForFunction(()=>document.getElementById('lb-img').naturalWidth>0&&V.loadedTok===V.loadTok&&V.fitW>0);
  }
  async function saved(page){
    await page.waitForFunction(()=>[...MARK_DAYS.values()].every(d=>[...d.jobs.values()].every(j=>!j.dirty&&!j.busy)));
  }
  const list=page=>page.evaluate(()=>JSON.parse(JSON.stringify(markList())));
  const point=async(page,st)=>{const r=await page.locator('#lb-img').boundingBox();return {
    x:r.x+(st.pts[0][0]+st.pts[1][0])/2*r.width,y:r.y+(st.pts[0][1]+st.pts[1][1])/2*r.height};};
  let [ctx,page]=await context();
  try{
    await page.goto(base+'/economy');await open(page);
    const prior=await page.locator('#lb-stage').evaluate(el=>getComputedStyle(el).cursor);
    let r=await page.locator('#lb-img').boundingBox();
    await page.mouse.move(r.x+r.width*.25,r.y+r.height*.25);await page.keyboard.press('1');
    let rows=await list(page),what=rows[0];
    check(rows.length===1&&what.t==='sticker'&&what.label==='WHAT','1 immediately stamps WHAT without a click');
    check(Math.abs((what.pts[0][0]+what.pts[1][0])/2-.25)<.01,'stamp is centered at the mouse');
    check(await page.evaluate(()=>STICK.active&&V.hand&&!M.on),'sticker movement preserves hand/pen state');
    check(await page.locator('#lb-stage').evaluate(el=>getComputedStyle(el).cursor)==='move','movement cursor shown');
    check(await page.locator('#lb-stickers').evaluate(el=>getComputedStyle(el).opacity==='1'),'sticker text has full opacity');
    await page.keyboard.press('Escape');
    check(await page.locator('#lb-stage').evaluate(el=>getComputedStyle(el).cursor)===prior,'Escape restores previous hand cursor');
    check(await page.evaluate(()=>!document.getElementById('lb').hidden&&!STICK.active),'Escape keeps the viewer and sticker');
    const start=await point(page,what),beforePan=await page.evaluate(()=>[V.tx,V.ty]);
    await page.mouse.move(start.x,start.y);await page.mouse.down();
    await page.mouse.move(start.x+r.width*.12,start.y+r.height*.10,{steps:8});await page.mouse.up();
    rows=await list(page);what=rows[0];
    check(what.pts[0][0]>.3&&what.pts[0][1]>.3,'existing sticker can be dragged again');
    assert.deepEqual(await page.evaluate(()=>[V.tx,V.ty]),beforePan);check(true,'dragging a sticker does not pan the newspaper');
    await page.mouse.move((await point(page,what)).x,(await point(page,what)).y);await page.mouse.down();
    await page.mouse.move(start.x+r.width*.15,start.y+r.height*.12);await page.keyboard.press('Escape');
    const fixed=JSON.stringify((await list(page))[0].pts);
    await page.mouse.move(start.x+r.width*.22,start.y+r.height*.20);await page.mouse.up();
    check(JSON.stringify((await list(page))[0].pts)===fixed,'Escape stops an active drag at its current position');
    await page.mouse.move(r.x+r.width*.65,r.y+r.height*.5);await page.keyboard.press('2');await page.keyboard.press('3');
    rows=await list(page);check(rows.map(s=>s.label).join(',')==='WHAT,WHY,HOW','2 and 3 stamp WHY and HOW');
    await page.keyboard.press('ArrowRight');await page.keyboard.press('Escape');await saved(page);
    const count=rows.length;
    await page.evaluate(()=>{document.getElementById('tn-panel').hidden=false;document.getElementById('tn-q').focus();});
    await page.keyboard.type('123');
    check(await page.locator('#tn-q').inputValue()==='123'&&(await list(page)).length===count,'typing 123 in a text input does not stamp');
    await page.evaluate(()=>{document.getElementById('tn-panel').hidden=true;document.getElementById('tn-q').blur();});
    await page.evaluate(()=>document.dispatchEvent(new KeyboardEvent('keydown',{key:'1',ctrlKey:true,bubbles:true})));
    check((await list(page)).length===count,'modified numeric shortcuts are ignored');
    await page.evaluate(()=>{setPen(true);setHand(false,true);});
    const penCursor=await page.locator('#lb-stage').evaluate(el=>getComputedStyle(el).cursor);
    r=await page.locator('#lb-img').boundingBox();await page.mouse.move(r.x+r.width*.7,r.y+r.height*.6);
    await page.keyboard.press('1');await page.keyboard.press('Escape');
    check(await page.evaluate(()=>M.on&&!V.hand&&!STICK.active),'Escape restores the previous pen tool');
    check(await page.locator('#lb-stage').evaluate(el=>getComputedStyle(el).cursor)===penCursor,'previous pen cursor is restored');
    r=await page.locator('#lb-img').boundingBox();
    await page.mouse.move(r.x+r.width*.2,r.y+r.height*.8);await page.mouse.down();await page.mouse.move(r.x+r.width*.5,r.y+r.height*.8,{steps:6});await page.mouse.up();
    check((await list(page)).at(-1).t==='line','normal highlighting works after Escape');
    await page.evaluate(()=>zoomAt(1.7));
    await page.waitForFunction(()=>Math.abs(document.getElementById('lb-img').getBoundingClientRect().width-document.getElementById('lb-stickers').getBoundingClientRect().width)<1);
    check(true,'sticker layer follows image zoom');
    const exported=await page.evaluate(async()=>{
      const cv=await renderPage(V.list[V.i]),st=markList().find(s=>s.t==='sticker'),[a,b]=st.pts;
      return [...cv.getContext('2d').getImageData(Math.floor((a[0]+(b[0]-a[0])*.08)*cv.width),Math.floor((a[1]+(b[1]-a[1])*.5)*cv.height),1,1).data];
    });
    check(exported[2]>exported[0]&&exported[3]===255,'image/PDF rendering includes opaque colored stickers');
    await saved(page);const persisted=await list(page);
    await page.reload();await open(page);
    assert.deepEqual(await list(page),persisted);check(true,'admin stickers and pen marks survive reload');
    await page.evaluate(()=>{setPen(true);setHand(false,true);setErase(true);});
    const st=(await list(page)).find(s=>s.t==='sticker'),hit=await point(page,st);
    const before=(await list(page)).filter(s=>s.t==='sticker').length;
    await page.mouse.click(hit.x,hit.y);await saved(page);
    check((await list(page)).filter(s=>s.t==='sticker').length===before-1,'eraser removes a sticker inside its rectangle');
    await page.evaluate(()=>setErase(false));
    const beforeUndo=(await list(page)).length;await page.keyboard.press('3');await page.keyboard.press('Control+z');
    check((await list(page)).length===beforeUndo,'undo removes the last added sticker');await saved(page);
    await page.evaluate(()=>{finishStickerMode();closeViewer();drawSideMarks();});
    await page.waitForFunction(()=>document.querySelector('.side-stickers')?.width>0);
    check(await page.locator('.side-stickers').first().evaluate(el=>getComputedStyle(el).mixBlendMode==='normal'&&getComputedStyle(el).opacity==='1'),'article previews use an opaque sticker layer');
    const outsideCount=(await list(page)).length;await page.keyboard.press('1');
    check((await list(page)).length===outsideCount,'shortcuts are inactive outside the paper viewer');
    await ctx.close();admin=false;
    [ctx,page]=await context({width:390,height:844});
    await page.goto(base+'/economy');await open(page,true);
    const requests=posts;await page.locator('#lb-sticker-what').click();
    check((await list(page))[0].label==='WHAT','toolbar can add stickers on a narrow screen');
    await page.keyboard.press('Escape');
    check(await page.evaluate(()=>M.on&&!V.hand),'mobile toolbar preserves previous pen mode after Escape');
    const toolbar=await page.locator('#lb-tools').boundingBox();
    check(toolbar.x>=0&&toolbar.x+toolbar.width<=391,'sticker toolbar does not overflow the screen');
    check(posts===requests,'guest stickers are not sent to admin storage');
    await page.reload();await open(page,true);
    check((await list(page)).length===0,'guest stickers follow existing temporary-mark lifetime');
    check(errors.length===0,'no browser script errors: '+errors.join(';'));
    console.log('PASS: '+checks+' sticker browser checks');
  }finally{await ctx.close();await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
