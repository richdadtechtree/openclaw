/* Charles customization tab: real gate cookies, actual shared editor in an iframe. */
const {chromium}=require('playwright'),{spawn}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const port=9400+Math.floor(Math.random()*400),base='http://localhost:'+port,cookiesFile=path.join(os.tmpdir(),'charles-custom-'+port+'.json');
const server=spawn('python3',[path.join(__dirname,'challenge_demo_server.py'),'--port',String(port),'--cookies',cookiesFile,'--today','2026-11-04'],{stdio:['ignore','inherit','inherit']});
let browser,checks=0;const errors=[],restricted=[],writes=[];
const check=(v,label)=>{assert.ok(v,label);checks++;console.log('OK '+label);};
(async()=>{
  try{
    let up=false;
    for(let i=0;i<80;i++){
      try{if((await fetch(base+'/privacy')).ok){up=true;break;}}catch(e){}
      await new Promise(r=>setTimeout(r,250));
    }
    assert.ok(up,'challenge demo server starts');
    const cookies=JSON.parse(fs.readFileSync(cookiesFile,'utf8'));
    browser=await chromium.launch({headless:true});
    for(const width of [1280,390]){
      const context=await browser.newContext({viewport:{width,height:width===390?844:900},acceptDownloads:true});
      await context.addCookies([{name:'gate_sess',value:cookies.b,url:base}]);
      await context.route('https://**/*',r=>r.abort());
      const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
      page.on('request',req=>{
        const u=new URL(req.url());
        if(u.origin!==base)return;
        if(/^\/(?:economy\/data|api\/news\/|gate\/theme)/.test(u.pathname))restricted.push(u.pathname);
        if(req.method()==='POST'&&u.pathname.startsWith('/api/challenge/'))writes.push(u.pathname);
      });
      await page.goto(base+'/challenge');await page.waitForSelector('.tile');
      check(await page.locator('#challenge-custom-frame').getAttribute('src')===null,'custom editor loads only when selected: '+width);
      await page.locator('#v-custom').click();
      const frameUI=page.frameLocator('#challenge-custom-frame');
      await frameUI.locator('#custom-drop').waitFor();
      const frame=page.frame({url:base+'/challenge/customize'});
      check(await page.locator('#v-custom').getAttribute('aria-selected')==='true'&&await page.locator('#daycard').isHidden()&&await page.locator('#glosscard').isHidden(),'custom tab hides other challenge views: '+width);
      check(await frame.evaluate(()=>window.__CUSTOM_ONLY&&document.body.classList.contains('custom-only')),'uses the shared customization-only mode: '+width);
      check(await frameUI.locator('#feed').isHidden()&&await frameUI.locator('#section-jump').isHidden()&&await frameUI.locator('.reader-actions').isHidden(),'custom mode contains no newspaper feed or account tools: '+width);
      check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'three challenge tabs fit the screen: '+width);
      const data=await frame.evaluate(()=>{
        const cv=document.createElement('canvas');cv.width=800;cv.height=1000;const ctx=cv.getContext('2d');
        ctx.fillStyle='white';ctx.fillRect(0,0,800,1000);ctx.fillStyle='black';ctx.font='32px sans-serif';ctx.fillText('Charles article',40,70);
        return Array.from(Uint8Array.from(atob(cv.toDataURL('image/png').split(',')[1]),c=>c.charCodeAt(0)));
      });
      await frameUI.locator('#custom-drop').click();
      await frame.evaluate(data=>{
        const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(data)],'capture.png',{type:'image/png'}));
        document.activeElement.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
        return CUSTOM.pending;
      },data);
      check(await frameUI.locator('.custom-card').count()===1,'Charles can paste screenshots: '+width);
      const transfer=await frame.evaluateHandle(data=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(data)],'drop.png',{type:'image/png'}));return dt;},data);
      await frameUI.locator('#custom-drop').dispatchEvent('drop',{dataTransfer:transfer});await frame.evaluate(()=>CUSTOM.pending);await transfer.dispose();
      check(await frameUI.locator('.custom-card').count()===2,'Charles can drag and drop images: '+width);
      await frameUI.locator('.custom-preview').first().click();
      await page.waitForFunction(()=>document.getElementById("customcard").classList.contains("custom-editor-open"));
      await frame.waitForFunction(()=>{
        const img=document.getElementById('lb-img'),r=img.getBoundingClientRect(),stage=document.getElementById('lb-stage').getBoundingClientRect();
        return V.custom&&M.on&&!V.hand&&img.naturalWidth>0&&V.loadedTok===V.loadTok&&innerWidth===parent.innerWidth&&innerHeight===parent.innerHeight&&
          Math.abs(stage.width-V.stage.w)<1&&Math.abs(stage.height-V.stage.h)<1&&Math.abs(r.width-V.fitW*V.zoom)<1&&Math.abs(r.height-V.fitH*V.zoom)<1;
      });
      check(await page.locator("#customcard").evaluate(el=>{const r=el.getBoundingClientRect();return r.top===0&&r.width===innerWidth&&r.height===innerHeight;}),
        "editing fills the screen above the challenge header: "+width);
      let r=await frameUI.locator('#lb-img').boundingBox();
      await page.mouse.move(r.x+r.width*.2,r.y+r.height*.7);await page.mouse.down();await page.mouse.move(r.x+r.width*.7,r.y+r.height*.7,{steps:6});await page.mouse.up();
      for(const [key,x,y]of [['1',.25,.25],['2',.5,.3],['3',.7,.4],['4',.4,.55]]){
        r=await frameUI.locator('#lb-img').boundingBox();await page.mouse.move(r.x+r.width*x,r.y+r.height*y);await page.keyboard.press(key);
      }
      check(await frame.evaluate(()=>markList().map(s=>s.label||s.t).join(',')==='line,WHAT,WHY,HOW,CHECK'),'Charles editor supports highlights and all four stamps: '+width);
      check(await frame.evaluate(()=>STICKER_COLORS.CHECK==='#dc2626'),'CHECK keeps the same vivid red style: '+width);
      await page.keyboard.press('Escape');check(await frame.evaluate(()=>M.on&&!V.hand&&!STICK.active),'Escape restores the drawing tool: '+width);
      const stamp=await frame.evaluate(()=>JSON.parse(JSON.stringify(markList().find(s=>s.label==='CHECK'))));r=await frameUI.locator('#lb-img').boundingBox();
      const x=r.x+(stamp.pts[0][0]+stamp.pts[1][0])/2*r.width,y=r.y+(stamp.pts[0][1]+stamp.pts[1][1])/2*r.height;
      await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+20,y+10,{steps:4});await page.mouse.up();await page.keyboard.press('Escape');
      check(await frame.evaluate(before=>markList().find(s=>s.label==='CHECK').pts[0][0]>before,stamp.pts[0][0]),'CHECK can be moved in the Charles editor: '+width);
      await page.keyboard.press('Delete');
      const why=await frame.evaluate(()=>JSON.parse(JSON.stringify(markList().find(s=>s.label==='WHY'))));r=await frameUI.locator('#lb-img').boundingBox();
      await page.mouse.click(r.x+(why.pts[0][0]+why.pts[1][0])/2*r.width,r.y+(why.pts[0][1]+why.pts[1][1])/2*r.height);
      check(await frame.evaluate(()=>M.erase&&!markList().some(s=>s.label==='WHY')),'Delete eraser removes custom stamps: '+width);
      await frameUI.locator('#lb-dl').click();
      let waiting=page.waitForEvent('download');await frameUI.locator('#lb-dl-img').click();let download=await waiting;
      check(fs.readFileSync(await download.path()).subarray(0,2).equals(Buffer.from([255,216])),'Charles downloads an edited JPG: '+width);
      waiting=page.waitForEvent('download');await frameUI.locator('#lb-dl-pdf').click();download=await waiting;
      const pdf=fs.readFileSync(await download.path());check(pdf.subarray(0,5).toString()==='%PDF-'&&/\/Count 2\b/.test(pdf.toString('latin1')),'Charles downloads custom images as a PDF: '+width);
      const before=await frame.evaluate(()=>JSON.stringify(CUSTOM.marks));await frameUI.locator('#lb-close').click();
      await page.waitForFunction(()=>!document.getElementById('customcard').classList.contains('custom-editor-open')&&document.body.style.overflow!=='hidden');
      await page.locator('#v-day').click();check(await page.locator('#customcard').isHidden()&&await page.locator('#daycard').isVisible(),'today newspaper tab still works: '+width);
      await page.locator('#v-custom').click();check(await frame.evaluate(()=>JSON.stringify(CUSTOM.marks))===before,'switching tabs preserves pasted images and edits: '+width);
      await page.locator('#v-gloss').click();check(await page.locator('#glosscard').isVisible()&&await page.locator('#customcard').isHidden(),'cohort glossary tab still works: '+width);
      await page.locator('#v-custom').click();check(await frameUI.locator('.custom-card').count()===2,'glossary roundtrip preserves the custom workspace: '+width);
      const day=await (await context.request.get(base+'/api/challenge/day?date=2026-11-04')).json();
      check(Object.keys(day.mine).length===0&&day.others.locked,'custom editing does not submit a challenge article or unlock cohort posts: '+width);
      check((await context.request.get(base+'/api/news/today')).status()===403,'Charles newspaper data permission remains unchanged: '+width);
      check(restricted.length===0&&writes.length===0,'standalone editor never requests restricted newspaper data or saves challenge posts: '+width);
      await page.goto(base+'/challenge#customize');await page.reload();await frameUI.locator('#custom-drop').waitFor();
      check(await page.locator('#v-custom').getAttribute('aria-selected')==='true'&&await frameUI.locator('.custom-card').count()===0,'customize link opens directly with the stated tab-only lifetime: '+width);
      await context.close();
    }
    check(errors.length===0,'no browser script errors: '+errors.join(';'));
    console.log('PASS: '+checks+' Charles customization browser checks');
  }finally{
    if(browser)await browser.close();server.kill('SIGTERM');try{fs.unlinkSync(cookiesFile);}catch(e){}
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
