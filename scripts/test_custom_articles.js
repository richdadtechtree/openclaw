/* Custom article image input/edit/export: real Chromium, no external network. */
const {chromium}=require('playwright');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const html=fs.readFileSync(path.join(__dirname,'../stock/slack_digest_live.html'),'utf8');
let admin=false,posts=0,customPosts=0,checks=0;const stored=new Map();
const server=http.createServer((req,res)=>{
  const u=new URL(req.url,'http://localhost'),day=u.searchParams.get('date')||'2026-11-04';
  const send=(type,body,code=200)=>{res.writeHead(code,{'Content-Type':type});res.end(body);};
  const json=(v,code=200)=>send('application/json',JSON.stringify(v),code);
  if(u.pathname==='/economy')return send('text/html; charset=utf-8',html);
  if(u.pathname==='/economy/data')return json({date:day,messages:[{ts:day+'T06:00:00+09:00',source:'user',kind:'text',
    text:'[신문요약 1/1] '+day+'\n\n1. 원래 신문 기사\n• 사진: 01\n• WHAT: 사실입니다.\n• WHY: 원인입니다.\n• HOW: 경과입니다.'}]});
  if(u.pathname==='/api/news/today')return json({ok:true,ready:true,date:day,count:2,images:[1,2].map(n=>({name:'0'+n+'.jpg',url:'/paper.svg',thumb:'/paper.svg',download_url:'/paper.svg'}))});
  if(u.pathname==='/paper.svg')return send('image/svg+xml','<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1800"><rect width="1200" height="1800" fill="white"/></svg>');
  if(u.pathname==='/api/news/marks'){
    if(req.method==='GET')return admin?json({ok:true,pages:Object.fromEntries(stored)}):json({ok:false},403);
    posts++;let raw='';req.on('data',b=>raw+=b);req.on('end',()=>{
      const b=JSON.parse(raw);if(b.page.startsWith('custom-'))customPosts++;
      if(!admin)return json({ok:false},403);
      stored.set(b.page,{strokes:b.strokes,revision:b.revision+1});json({ok:true,revision:b.revision+1});
    });return;
  }
  return json({ok:false},403);
});
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser=await chromium.launch({headless:true}),base='http://127.0.0.1:'+server.address().port,errors=[];
  let ctx,page;
  const check=(v,label)=>{assert.ok(v,label);checks++;console.log('OK '+label);};
  async function context(viewport={width:1280,height:900}){
    ctx=await browser.newContext({viewport,acceptDownloads:true});await ctx.route('https://**/*',r=>r.abort());
    page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto(base+'/economy');
    await page.waitForFunction(()=>newsState.images.length===2&&markDay&&['admin','guest'].includes(markDay.mode));
  }
  async function imported(count){
    await page.evaluate(()=>CUSTOM.pending);
    await page.waitForFunction(n=>CUSTOM.items.length===n&&document.querySelectorAll('.custom-card').length===n,count);
  }
  async function viewer(){
    await page.waitForFunction(()=>!document.getElementById('lb').hidden&&document.getElementById('lb-img').naturalWidth>0&&V.loadedTok===V.loadTok&&V.fitW>0);
    await page.waitForFunction(()=>{const r=document.getElementById('lb-img').getBoundingClientRect();return Math.abs(r.width-V.fitW*V.zoom)<1&&Math.abs(r.height-V.fitH*V.zoom)<1;});
  }
  async function stamp(key,x=.5,y=.5){
    const r=await page.locator('#lb-img').boundingBox();await page.mouse.move(r.x+r.width*x,r.y+r.height*y);await page.keyboard.press(key);
  }
  async function line(){
    const r=await page.locator('#lb-img').boundingBox();
    await page.mouse.move(r.x+r.width*.2,r.y+r.height*.7);await page.mouse.down();
    await page.mouse.move(r.x+r.width*.7,r.y+r.height*.7,{steps:7});await page.mouse.up();
  }
  const marks=()=>page.evaluate(()=>JSON.parse(JSON.stringify(markList())));
  async function bytes(download){return fs.readFileSync(await download.path());}
  try{
    await context();
    const png=Buffer.from(await page.evaluate(()=>{
      const c=document.createElement('canvas');c.width=800;c.height=1200;const x=c.getContext('2d');
      x.fillStyle='white';x.fillRect(0,0,800,1200);x.fillStyle='black';x.font='bold 32px sans-serif';x.fillText('My article',50,80);
      return c.toDataURL('image/png').split(',')[1];
    }),'base64');
    const data=Array.from(png);
    await page.evaluate(()=>{window.jumpCalls=[];const original=window.scrollTo.bind(window);window.scrollTo=o=>{window.jumpCalls.push(o);return original(o);};});
    await page.locator('#section-jump [data-section=customize]').click();
    check(await page.evaluate(()=>jumpCalls.at(-1).behavior==='instant'&&document.querySelector('#section-jump [aria-current=location]').dataset.section==='customize'),
      'left customization menu jumps immediately to its section');
    check(await page.locator('#customize').isVisible(),'custom workspace is available when podcast/editorial are absent');
    await page.locator('#datepick').focus();
    const ignored=await page.evaluate(data=>{
      const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(data)],'capture.png',{type:'image/png'}));
      const event=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true});document.activeElement.dispatchEvent(event);return event.defaultPrevented;
    },data);
    check(!ignored&&await page.evaluate(()=>CUSTOM.items.length===0),'pasting outside the customization area is not intercepted');
    await page.locator('#custom-drop').click();
    const pasted=await page.evaluate(data=>{
      const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(data)],'capture.png',{type:'image/png'}));
      const event=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true});document.activeElement.dispatchEvent(event);return event.defaultPrevented;
    },data);
    await imported(1);check(pasted,'Ctrl+V image paste in the focused area adds an image');
    const dt=await page.evaluateHandle(data=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(data)],'drop.png',{type:'image/png'}));return dt;},data);
    await page.locator('#custom-drop').dispatchEvent('dragover',{dataTransfer:dt});
    check(await page.locator('#custom-drop').evaluate(el=>el.classList.contains('drag-over')),'drag feedback highlights the drop area');
    await page.locator('#custom-drop').dispatchEvent('drop',{dataTransfer:dt});await imported(2);
    check(await page.locator('#custom-drop').evaluate(el=>!el.classList.contains('drag-over')),'drop imports an actual image and clears drag feedback');
    await dt.dispose();
    await page.locator('#custom-files').setInputFiles([
      {name:'<img onerror=alert(1)>.png',mimeType:'image/png',buffer:png},{name:'fourth.png',mimeType:'image/png',buffer:png}]);
    await imported(4);
    check(await page.locator('.custom-card-title').nth(2).textContent()==='<img onerror=alert(1)>.png'&&await page.locator('.custom-card-title img').count()===0,'multi-file selection keeps filenames as safe text');
    await page.locator('#custom-files').setInputFiles({name:'bad.svg',mimeType:'image/svg+xml',buffer:Buffer.from('<svg/>')});
    await page.evaluate(()=>CUSTOM.pending);check(await page.evaluate(()=>CUSTOM.items.length===4),'unsupported image format leaves existing images intact');
    await page.locator('#custom-files').setInputFiles({name:'broken.png',mimeType:'image/png',buffer:Buffer.from('broken')});
    await page.evaluate(()=>CUSTOM.pending);check(await page.evaluate(()=>CUSTOM.items.length===4),'undecodable image shows an error without adding a broken card');
    await page.locator('#custom-files').setInputFiles({name:'huge.png',mimeType:'image/png',buffer:Buffer.alloc(20*1024*1024+1)});
    await page.evaluate(()=>CUSTOM.pending);check(/20MB/.test(await page.locator('#custom-status').textContent()),'oversized image has a clear size message');
    const previousPosts=posts,newsBefore=await page.evaluate(()=>JSON.stringify(M.marks));
    await page.locator('.custom-preview').first().click();await viewer();
    check(await page.evaluate(()=>V.custom&&M.on&&!V.hand&&document.getElementById('lb-note').hidden),'custom image opens with editing ready and no unrelated newspaper summary');
    check(await page.evaluate(()=>document.getElementById('lb-img').naturalWidth===800),'viewer uses the imported image');
    await line();await stamp('1',.2,.2);await stamp('2',.5,.3);await stamp('3',.7,.4);await stamp('4',.4,.5);
    check((await marks()).map(s=>s.t==='sticker'?s.label:s.t).join(',')==='line,WHAT,WHY,HOW,CHECK','imported image supports highlights and all four stamps');
    const what=(await marks()).find(s=>s.label==='WHAT');let r=await page.locator('#lb-img').boundingBox();
    await page.mouse.move(r.x+(what.pts[0][0]+what.pts[1][0])/2*r.width,r.y+(what.pts[0][1]+what.pts[1][1])/2*r.height);
    await page.mouse.down();await page.mouse.move(r.x+r.width*.3,r.y+r.height*.25,{steps:5});await page.mouse.up();await page.keyboard.press('Escape');
    check((await marks()).find(s=>s.label==='WHAT').pts[0][0]>what.pts[0][0],'stamps can be dragged on imported images');
    check(await page.evaluate(()=>M.on&&!V.hand&&!STICK.active),'Escape restores the pen after moving a custom stamp');
    await page.keyboard.press('Delete');
    const why=(await marks()).find(s=>s.label==='WHY');r=await page.locator('#lb-img').boundingBox();
    await page.mouse.click(r.x+(why.pts[0][0]+why.pts[1][0])/2*r.width,r.y+(why.pts[0][1]+why.pts[1][1])/2*r.height);
    check(!(await marks()).some(s=>s.label==='WHY'),'Delete eraser removes a custom stamp');
    await page.keyboard.press('Control+z');check(!(await marks()).some(s=>s.label==='CHECK'),'undo works on custom marks');
    await stamp('4',.4,.5);await page.keyboard.press('Escape');
    const rendered=await page.evaluate(async()=>{
      const cv=await renderPage(V.list[V.i]),x=cv.getContext('2d'),st=markList().find(s=>s.label==='WHAT'),[a,b]=st.pts;
      return {w:cv.width,h:cv.height,line:[...x.getImageData(400,840,1,1).data],sticker:[...x.getImageData(Math.round((a[0]+(b[0]-a[0])*.08)*800),Math.round((a[1]+b[1])/2*1200),1,1).data]};
    });
    check(rendered.w===800&&rendered.h===1200&&rendered.line[1]<220&&rendered.sticker.join(',')==='29,78,216,255','export includes imported pixels, highlights, and opaque stickers');
    await page.locator('#lb-dl').click();
    let downloadPromise=page.waitForEvent('download');await page.locator('#lb-dl-img').click();let download=await downloadPromise;
    check((await bytes(download)).subarray(0,2).equals(Buffer.from([255,216]))&&/^custom_/.test(download.suggestedFilename()),'viewer downloads the edited custom image as JPG');
    downloadPromise=page.waitForEvent('download');await page.locator('#lb-dl-pdf').click();download=await downloadPromise;
    let pdf=await bytes(download);
    check(pdf.subarray(0,5).toString()==='%PDF-'&&/\/Count 4\b/.test(pdf.toString('latin1')),'full PDF contains the four custom images instead of newspaper pages');
    downloadPromise=page.waitForEvent('download');await page.locator('#lb-dl-pdfm').click();download=await downloadPromise;
    check(/\/Count 1\b/.test((await bytes(download)).toString('latin1')),'marked-only PDF includes the edited custom image');
    downloadPromise=page.waitForEvent('download');await page.locator('#lb-dl-orig').click();download=await downloadPromise;
    check((await bytes(download)).equals(png),'original image download preserves the source file');
    const edited=await marks();await page.locator('#lb-close').click();
    check(await page.evaluate(()=>!V.custom)&&posts===previousPosts&&customPosts===0,'custom edits never write newspaper annotations');
    check(await page.evaluate(()=>JSON.stringify(M.marks))===newsBefore&&await page.locator('#feed .brf-check').count()===0,'custom CHECK never changes newspaper marks or article badges');
    await page.locator('.custom-preview').first().click();await viewer();
    assert.deepEqual(await marks(),edited);check(true,'custom annotations survive closing and reopening the image');
    await page.keyboard.press('PageDown');await viewer();
    check((await marks()).length===0&&await page.evaluate(()=>V.list[V.i].fileName==='drop.png'),'custom images keep separate annotations and support next/previous');
    await stamp('4');await page.keyboard.press('Escape');
    page.once('dialog',d=>d.accept());await page.locator('#lb-clear').click();check((await marks()).length===0,'clear removes only the current custom image annotations');
    await page.locator('#lb-close').click();
    downloadPromise=page.waitForEvent('download');await page.locator('.custom-card-actions').first().getByRole('button',{name:'JPG 다운로드'}).click();download=await downloadPromise;
    check((await bytes(download)).subarray(0,2).equals(Buffer.from([255,216])),'custom card can download edits without opening the viewer');
    await page.locator('.custom-card-actions').nth(1).getByRole('button',{name:'삭제',exact:true}).click();
    check(await page.evaluate(()=>CUSTOM.items.length===3)&&await page.locator('.custom-card').count()===3,'removing an imported article updates the list');
    await page.locator('#edtog [data-ed=online]').click();
    await page.waitForFunction(()=>document.getElementById('section-jump').dataset.edition==='online');
    check(await page.locator('#section-jump [data-section=customize]').isEnabled()&&await page.locator('.custom-card').count()===3,'custom workspace remains available in the online edition');
    await ctx.close();admin=true;await context();
    check(await page.locator('.custom-card').count()===0,'imported photos have the stated tab-only lifetime');
    await page.locator('#custom-files').setInputFiles({name:'admin.png',mimeType:'image/png',buffer:png});await imported(1);
    await page.locator('.custom-preview').click();await viewer();await line();await stamp('4');await page.locator('#lb-close').click();
    check(posts===previousPosts&&customPosts===0,'admin custom edits also stay out of newspaper storage');
    await page.evaluate(()=>{openViewer(0,{pen:true});setHand(false,true);});await viewer();await line();
    await page.waitForFunction(()=>[...MARK_DAYS.values()].every(d=>[...d.jobs.values()].every(j=>!j.dirty&&!j.busy)));
    check(posts>previousPosts&&stored.get('01.jpg').strokes.length===1,'normal admin newspaper annotations still save after custom editing');
    await ctx.close();admin=false;await context({width:390,height:844});
    await page.locator('#section-jump [data-section=customize]').click();
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.getElementById('section-jump').getBoundingClientRect().right<=innerWidth),'four-item navigation fits the mobile screen');
    await page.locator('#custom-files').setInputFiles({name:'mobile.png',mimeType:'image/png',buffer:png});await imported(1);
    await page.locator('.custom-preview').click();await viewer();await stamp('4');
    await page.locator('#lb-hand-float').click();
    check(await page.evaluate(()=>V.hand&&M.on&&!STICK.active&&V.pts.size===0&&markList().length===1),'floating hand overrides a selected center CHECK without moving or erasing it');
    await page.locator('#lb-hand-float').click();
    check(await page.evaluate(()=>!V.hand&&M.on&&markList().length===1),'floating hand returns custom photos to the pen');
    await page.keyboard.press('Escape');
    check((await marks())[0].label==='CHECK','mobile custom images support stickers');
    check(errors.length===0,'no browser script errors: '+errors.join(';'));
    console.log('PASS: '+checks+' customization browser checks');
  }finally{await ctx.close();await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
