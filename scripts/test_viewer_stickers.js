/* WHAT/WHY/HOW/CHECK stickers: real Chromium, mock price-free newspaper server. */
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
    check(await page.locator('#lb-stickers').evaluate(el=>getComputedStyle(el).opacity==='1'),'sticker layer preserves its original color');
    await page.keyboard.press('Escape');
    check(await page.locator('#lb-stage').evaluate(el=>getComputedStyle(el).cursor)===prior,'Escape restores previous hand cursor');
    check(await page.evaluate(()=>!document.getElementById('lb').hidden&&!STICK.active),'Escape keeps the viewer and sticker');
    const start=await point(page,what),originalPoint=what.pts[0].slice(),beforePan=await page.evaluate(()=>[V.tx,V.ty]);
    await page.mouse.move(start.x,start.y);await page.mouse.down();
    await page.mouse.move(start.x+r.width*.12,start.y+r.height*.10,{steps:8});await page.mouse.up();
    rows=await list(page);what=rows[0];
    check(Math.abs(what.pts[0][0]-originalPoint[0]-.12)<.01&&Math.abs(what.pts[0][1]-originalPoint[1]-.10)<.01,'existing sticker can be dragged again: '+JSON.stringify({before:originalPoint,after:what.pts[0]}));
    assert.deepEqual(await page.evaluate(()=>[V.tx,V.ty]),beforePan);check(true,'dragging a sticker does not pan the newspaper');
    await page.mouse.move((await point(page,what)).x,(await point(page,what)).y);await page.mouse.down();
    await page.mouse.move(start.x+r.width*.15,start.y+r.height*.12);await page.keyboard.press('Escape');
    const fixed=JSON.stringify((await list(page))[0].pts);
    await page.mouse.move(start.x+r.width*.22,start.y+r.height*.20);await page.mouse.up();
    check(JSON.stringify((await list(page))[0].pts)===fixed,'Escape stops an active drag at its current position');
    await page.mouse.move(r.x+r.width*.65,r.y+r.height*.5);await page.keyboard.press('2');await page.keyboard.press('3');
    rows=await list(page);check(rows.map(s=>s.label).join(',')==='WHAT,WHY,HOW','2 and 3 stamp WHY and HOW');
    await page.mouse.move(r.x+r.width*.3,r.y+r.height*.6);await page.keyboard.press('4');
    rows=await list(page);
    check(rows.at(-1).label==='CHECK'&&rows.at(-1).c==='#dc2626','4 stamps CHECK with a vivid red color');
    const legacy=await page.evaluate(()=>{
      const st={t:"sticker",label:"CHECK",c:"#b45309",pts:[[.2,.2],[.35,.24]]};
      const [a,b]=stickerBounds(st),cv=document.createElement("canvas");cv.width=1200;cv.height=1800;
      drawSticker(cv.getContext("2d"),st,1200,1800);
      return {width:(b[0]-a[0])/.15,height:(b[1]-a[1])/.04,
        color:[...cv.getContext("2d").getImageData(Math.round((a[0]+(b[0]-a[0])*.04)*1200),396,1,1).data]};
    });
    check(Math.abs(legacy.width-1.5)<.001&&Math.abs(legacy.height-1.5)<.001&&legacy.color.join(",")==="220,38,38,255",
      "previously saved CHECK stickers become 1.5 times larger and vivid red: "+JSON.stringify(legacy));
    const checkStamp=rows.at(-1),cp=await point(page,checkStamp);
    cp.x-=(checkStamp.pts[1][0]-checkStamp.pts[0][0])*r.width*.6;
    await page.mouse.move(cp.x,cp.y);await page.mouse.down();await page.mouse.move(cp.x+20,cp.y+10,{steps:4});await page.mouse.up();
    rows=await list(page);
    check(rows.at(-1).pts[0][0]>checkStamp.pts[0][0],'CHECK can be dragged from its enlarged outer area');
    await page.keyboard.press('ArrowRight');await page.keyboard.press('Escape');await saved(page);
    const count=rows.length;
    await page.evaluate(()=>{document.getElementById('tn-panel').hidden=false;document.getElementById('tn-q').focus();});
    await page.keyboard.type('1234');
    check(await page.locator('#tn-q').inputValue()==='1234'&&(await list(page)).length===count,'typing 1234 in a text input does not stamp');
    await page.keyboard.press('Home');await page.keyboard.press('Delete');
    check(await page.locator('#tn-q').inputValue()==='234'&&await page.evaluate(()=>!M.on&&!M.erase),
      'Delete edits text without activating the eraser');
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
    await page.evaluate(()=>setErase(true));
    r=await page.locator('#lb-img').boundingBox();
    await page.mouse.move(r.x+r.width*.72,r.y+r.height*.22);await page.keyboard.press('2');
    const eraserSticker=(await list(page)).at(-1),ep=await point(page,eraserSticker);
    await page.mouse.move(ep.x,ep.y);await page.mouse.down();await page.mouse.move(ep.x+20,ep.y+10,{steps:4});await page.mouse.up();
    check((await list(page)).at(-1).pts[0][0]>eraserSticker.pts[0][0],'sticker movement takes priority while the previous tool is eraser');
    await page.keyboard.press('Escape');
    check(await page.evaluate(()=>M.on&&M.erase&&!STICK.active),'Escape restores the previous eraser tool');
    await page.evaluate(()=>setErase(false));
    await page.evaluate(()=>zoomAt(1.7));
    await page.waitForFunction(()=>Math.abs(document.getElementById('lb-img').getBoundingClientRect().width-V.fitW*V.zoom)<1&&Math.abs(document.getElementById('lb-img').getBoundingClientRect().width-document.getElementById('lb-stickers').getBoundingClientRect().width)<1);
    check(true,'sticker layer follows image zoom');
    const exported=await page.evaluate(async()=>{
      const st=markList().find(s=>s.t==='sticker'),[a,b]=st.pts;
      const x=Math.floor(a[0]*1200),y=Math.floor(a[1]*1800),w=Math.ceil((b[0]-a[0])*1200),h=Math.ceil((b[1]-a[1])*1800);
      const samples=[];
      for(const label of Object.keys(STICKER_COLORS)){
        const layer=document.createElement("canvas");layer.width=1200;layer.height=1800;
        const context=layer.getContext("2d");
        drawSticker(context,{...st,label},1200,1800);
        const [sa,sb]=stickerBounds({...st,label}),sx=Math.floor(sa[0]*1200),sy=Math.floor(sa[1]*1800);
        const sw=Math.ceil((sb[0]-sa[0])*1200),sh=Math.ceil((sb[1]-sa[1])*1800);
        const pixels=context.getImageData(sx,sy,sw,sh).data;
        const expected=STICKER_COLORS[label].slice(1).match(/../g).map(v=>parseInt(v,16));
        let opaque=0,whiteText=0,colored=0;
        for(let row=Math.floor(sh*.2);row<sh*.8;row++)for(let col=Math.floor(sw*.1);col<sw*.9;col++){
          const i=(row*sw+col)*4;
          if(pixels[i+3]===255)opaque++;
          if(pixels[i]===255&&pixels[i+1]===255&&pixels[i+2]===255&&pixels[i+3]===255)whiteText++;
          if(expected.every((v,k)=>pixels[i+k]===v)&&pixels[i+3]===255)colored++;
        }
        samples.push({label,opaque,whiteText,colored,outside:context.getImageData(sx-2,sy-2,1,1).data[3]});
      }
      const cv=await renderPage(V.list[V.i]);
      const background=[...cv.getContext("2d").getImageData(x+Math.floor(w*.08),y+Math.floor(h*.5),1,1).data];
      return {samples,background};
    });
    check(exported.samples.every(s=>s.opaque>100&&s.whiteText>20&&s.colored>100&&s.outside===0),
      'all four stickers use opaque colored backgrounds and bold white text');
    check(exported.background.join(',')==='29,78,216,255',
      'image/PDF output preserves the high contrast sticker background');
    await saved(page);const persisted=await list(page);
    await page.reload();await open(page);
    assert.deepEqual(await list(page),persisted);check(true,'admin stickers including CHECK and pen marks survive reload');
    const beforeDelete=await list(page);
    await page.keyboard.press('Delete');
    check(await page.evaluate(()=>M.on&&M.erase&&!V.hand&&!STICK.active&&document.getElementById('lb-erase').getAttribute('aria-pressed')==='true'),
      'Delete activates the eraser from hand mode and opens its toolbar');
    assert.deepEqual(await list(page),beforeDelete);check(true,'Delete only activates the tool until a sticker is clicked');
    await page.keyboard.press('Delete');
    check(await page.evaluate(()=>M.erase),'pressing Delete again keeps the eraser active');
    const st=(await list(page)).find(s=>s.t==='sticker'),hit=await point(page,st);
    const before=(await list(page)).filter(s=>s.t==='sticker').length;
    await page.mouse.click(hit.x,hit.y);await saved(page);
    check((await list(page)).filter(s=>s.t==='sticker').length===before-1,'Delete eraser removes a clicked saved sticker');
    for(const [key,label] of [['1','WHAT'],['2','WHY'],['3','HOW'],['4','CHECK']]){
      const original=await list(page),rect=await page.locator('#lb-img').boundingBox();
      await page.mouse.move(rect.x+rect.width*.25,rect.y+rect.height*.15);
      await page.keyboard.press(key);
      check(await page.evaluate(()=>STICK.active),'sticker selected before Delete: '+label);
      await page.keyboard.press('Delete');
      check(await page.evaluate(()=>M.erase&&!STICK.active),'Delete leaves sticker movement and activates eraser: '+label);
      const added=(await list(page)).at(-1),p=await point(page,added);
      if(label==="CHECK"){
        const rect=await page.locator("#lb-img").boundingBox();
        p.x-=(added.pts[1][0]-added.pts[0][0])*rect.width*.6;
      }
      await page.mouse.click(p.x,p.y);await saved(page);
      assert.deepEqual(await list(page),original);
      check(true,'Delete eraser removes only the clicked '+label+' sticker');
    }
    const afterDelete=await list(page);await page.reload();await open(page);
    assert.deepEqual(await list(page),afterDelete);check(true,'deleted stickers remain removed after reload');
    await page.evaluate(()=>{setPen(true);setHand(false,true);setErase(false);});
    const beforeUndo=(await list(page)).length;await page.keyboard.press('3');await page.keyboard.press('Control+z');
    check((await list(page)).length===beforeUndo,'undo removes the last added sticker');await saved(page);
    await page.evaluate(()=>{finishStickerMode();closeViewer();drawSideMarks();});
    await page.waitForFunction(()=>document.querySelector('.side-stickers')?.width>0);
    check(await page.locator('.side-stickers').first().evaluate(el=>getComputedStyle(el).mixBlendMode==='normal'&&getComputedStyle(el).opacity==='1'),'article previews preserve solid sticker colors without highlight blending');
    const outsideCount=(await list(page)).length;await page.keyboard.press('1');
    check((await list(page)).length===outsideCount,'shortcuts are inactive outside the paper viewer');
    const outsideMode=await page.evaluate(()=>[M.on,M.erase]);
    await page.keyboard.press('Delete');
    assert.deepEqual(await page.evaluate(()=>[M.on,M.erase]),outsideMode);
    check(true,'Delete is inactive outside the paper viewer');
    await ctx.close();admin=false;
    [ctx,page]=await context({width:390,height:844});
    await page.goto(base+'/economy');await open(page,true);
    const requests=posts;await page.locator('#lb-sticker-check').click();
    check((await list(page))[0].label==='CHECK','toolbar can add CHECK on a narrow screen');
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
