/* 실제 Chromium에서 관리자 UI와 2% 구간 팝업 확인. 외부 시세/회원 서버는 호출하지 않는다. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {chromium} = require('playwright');
const html = fs.readFileSync(path.join(__dirname, '../stock/index.html'), 'utf8');
assert.equal(html, fs.readFileSync(path.join(__dirname, '../stock/templates/index.html'), 'utf8'));
let rows=[], indices={}, strategies=null, canManage=true, viewer='1', posts=[];
const makeRow=(rate,id=1,date='2026-11-03')=>({id,symbol:'AAPL',name:'애플',quote:{
  current:102,change_rate:rate,source:'TEST',currency:'USD',market_date:date,observed_at:Date.now()/1000}});
(async()=>{
  const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1280,height:900}});
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.hostname!=='127.0.0.1')return route.abort();
      if(!url.pathname.startsWith('/market/api/'))return route.continue();
      let body={status:'error',data:null};
      if(url.pathname==='/market/api/alerts'&&strategies)body={status:'success',data:strategies};
      if(url.pathname==='/market/api/indices')body={status:'success',data:indices};
      if(url.pathname==='/market/api/watchlist'){
        if(route.request().method()==='POST'){
          posts.push({data:route.request().postDataJSON(),headers:route.request().headers()});
          const d=posts.at(-1).data;
          if(d.action==='add')rows=[{...makeRow(0,2),symbol:d.symbol,name:d.name}];
          else rows=rows.filter(r=>r.id!==d.id);
        }
        body={ok:true,items:rows,can_manage:canManage,csrf:canManage?'test-csrf':'',viewer_key:viewer};
      }
      if(url.pathname==='/market/api/watchlist/quotes')body={ok:true,items:rows,step:2};
      return route.fulfill({json:body});
    });
    const base='http://127.0.0.1:'+server.address().port+'/market';
    const sync=async()=>{
      const done=page.waitForResponse(r=>r.url().endsWith('/market/api/watchlist/quotes'));
      await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
      await done;
      await page.waitForFunction(()=>document.querySelector('#watch-message').textContent.includes('관리자'));
    };
    rows=[makeRow(1.99)];
    await page.goto(base);
    await page.locator('#watch-form').waitFor({state:'visible'});
    await page.waitForFunction(()=>document.querySelector('#watch-grid').textContent.includes('1.99%'));
    assert.equal(await page.locator('.surge-popup').count(),0);
    for(const [rate,expected] of [[2,1],[2,1],[3.99,1],[4,2],[6.3,3],[3,3],[6.3,3],[8.01,3]]){
      rows=[makeRow(rate)];await sync();
      await page.waitForFunction(rate=>document.querySelector('#watch-grid').textContent.includes(rate.toFixed(2)+'%'),rate);
      await page.evaluate(async key=>{if(navigator.locks)await navigator.locks.request(key,()=>{});},'market.watch.rise.v1.'+viewer);
      assert.equal(await page.locator('.surge-popup').count(),expected,'rate '+rate);
    }
    assert.match(await page.locator('#surge-popups').textContent(),/\+8% 구간/);
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#watch-grid').textContent.includes('8.01%'));
    assert.equal(await page.locator('.surge-popup').count(),0,'reload must not repeat');
    rows=[makeRow(2,1,'2026-11-04')];await sync();
    await page.locator('.surge-popup').waitFor({state:'visible'});
    assert.match(await page.locator('.surge-popup').textContent(),/\+2% 구간/);
    await page.locator('.surge-popup button').click();
    assert.equal(await page.locator('.surge-popup').count(),0);
    const before=Date.now()/1000-300;
    rows=[{...makeRow(10),quote:{...makeRow(10).quote,observed_at:before}}];await sync();
    assert.equal(await page.locator('.surge-popup').count(),0,'stale quote cannot trigger');
    await page.locator('#watch-symbol').fill('TSLA');
    await page.locator('#watch-name').fill('<img src=x onerror=alert(1)>');
    await page.locator('#watch-form button').click();
    await page.waitForFunction(()=>document.querySelector('#watch-grid').textContent.includes('<img src=x'));
    assert.equal(posts.at(-1).headers['x-csrf-token'],'test-csrf');
    assert.equal(await page.locator('#watch-grid img').count(),0,'name must be text');

    // 지수 응답은 실제 화면의 갱신 흐름으로 넣어 모든 지수·ETF 팝업을 확인한다.
    await page.evaluate(()=>window.addEventListener('market-indices-updated',()=>window.__indexEvents=(window.__indexEvents||0)+1));
    const syncIndex=async(symbol,rate,source='Naver Finance',age=0,stamp=true)=>{
      indices={[symbol]:{current:6000,change_rate:rate,ath:9000,ath_change_rate:-33.33,source,
        ...(stamp?{observed_at:Date.now()/1000-age}:{})}};
      const before=await page.evaluate(()=>window.__indexEvents||0);
      await page.locator('#refresh-btn').click();
      await page.waitForFunction(n=>(window.__indexEvents||0)>n,before);
      await page.evaluate(async key=>{if(navigator.locks)await navigator.locks.request(key,()=>{});},'market.watch.rise.v1.'+viewer);
    };
    const closePopups=()=>page.evaluate(()=>document.querySelectorAll('.surge-popup button').forEach(b=>b.click()));
    for(const symbol of ['KOSPI','KOSDAQ','S&P 500','NASDAQ','QLD','TQQQ']){
      await closePopups();await syncIndex(symbol,2);
      assert.equal(await page.locator('.surge-popup').count(),1,'index popup: '+symbol);
      assert.ok((await page.locator('.surge-popup').textContent()).includes('('+symbol+')'));
      const unit=symbol==='QLD'||symbol==='TQQQ'?' USD':' pt';
      assert.ok((await page.locator('.surge-popup').textContent()).includes(unit),'correct price unit: '+symbol);
    }
    await closePopups();await syncIndex('KOSPI',2);
    assert.equal(await page.locator('.surge-popup').count(),0,'index repeated 2%');
    await syncIndex('KOSPI',4);
    assert.match(await page.locator('.surge-popup').textContent(),/\+4% 구간/);
    await closePopups();await syncIndex('KOSPI',3);await syncIndex('KOSPI',4);
    assert.equal(await page.locator('.surge-popup').count(),0,'index rebound');
    await syncIndex('S&P 500',10,'Korea Investment API');
    await syncIndex('NASDAQ',10,'Korea Investment API');
    assert.equal(await page.locator('.surge-popup').count(),0,'ETF approximations are not index alerts');
    await syncIndex('KOSPI',20,'Naver Finance',300);
    assert.equal(await page.locator('.surge-popup').count(),0,'stale index quote');
    await syncIndex('KOSPI',20,'Naver Finance',0,false);
    assert.equal(await page.locator('.surge-popup').count(),0,'missing index timestamp');


    // ATH 타겟은 현재 낙폭과 화면의 목표값으로 판단한다. 과거 triggered 값은 판정에 쓰지 않는다.
    const target=async(symbol,dd,ath=9000,stale=false)=>{
      const stages=symbol==='NASDAQ'?[-5,-10,-15,-20]:[-30,-40,-50,-60,-70];
      strategies={[symbol]:{drawdown:dd,ath,stages:stages.map(stage=>({stage,triggered:dd<=stage})),
        next_stage:stages.find(s=>dd>s)||null,gap_pp:1,done:stages.filter(s=>dd<=s).length,total:stages.length}};
      indices={[symbol]:{current:ath*(1+dd/100),change_rate:-1,ath,ath_change_rate:dd,source:'Naver Finance',
        observed_at:Date.now()/1000-(stale?300:0)}};
      const before=await page.evaluate(()=>window.__targetEvents||0);
      await page.locator('#refresh-btn').click();
      await page.waitForFunction(n=>(window.__targetEvents||0)>n,before);
      await page.evaluate(async key=>{if(navigator.locks)await navigator.locks.request(key,()=>{});},'market.watch.rise.v1.'+viewer);
    };
    await page.evaluate(()=>window.addEventListener('market-targets-updated',()=>window.__targetEvents=(window.__targetEvents||0)+1));
    await closePopups();await target('KOSPI',-29.99);
    assert.equal(await page.locator('.target-popup').count(),0,'before -30%');
    await target('KOSPI',-30);
    assert.match(await page.locator('.target-popup').textContent(),/ATH -30% 목표/);
    await closePopups();await target('KOSPI',-39.81);
    assert.equal(await page.locator('.target-popup').count(),0,'-39.81 is not -40');
    await target('KOSPI',-40);
    assert.match(await page.locator('.target-popup').textContent(),/ATH -40% 목표/);
    await closePopups();await target('KOSPI',-38);await target('KOSPI',-40);
    assert.equal(await page.locator('.target-popup').count(),0,'target rebound is suppressed');
    await target('KOSDAQ',-42.71);
    assert.match(await page.locator('.target-popup').textContent(),/ATH -40% 목표/);
    await closePopups();await target('NASDAQ',-9.23);
    assert.match(await page.locator('.target-popup').textContent(),/ATH -5% 목표/);
    await closePopups();await target('NASDAQ',-10);
    assert.match(await page.locator('.target-popup').textContent(),/ATH -10% 목표/);
    await closePopups();await target('KOSPI',-50,9000,true);
    assert.equal(await page.locator('.target-popup').count(),0,'stale target excluded');
    await target('KOSPI',-30,10000);
    assert.match(await page.locator('.target-popup').textContent(),/ATH -30% 목표/);
    await closePopups();
    await page.evaluate(()=>scrollTo({top:1000,behavior:'instant'}));
    await page.waitForFunction(()=>Math.abs(document.querySelector('.sitenav').getBoundingClientRect().top)<1);
    assert.equal(await page.locator('.sitenav a[aria-current=page]').isVisible(),true,'market navigation stays visible');

    canManage=false;viewer='2';await sync();
    await page.locator('#watch-form').waitFor({state:'hidden'});
    assert.equal(await page.locator('#watch-grid button').count(),0,'reader cannot delete');
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile overflow');
    await page.evaluate(()=>scrollTo({top:1000,behavior:'instant'}));
    await page.waitForFunction(()=>Math.abs(document.querySelector('.sitenav').getBoundingClientRect().top)<1);
    assert.equal(await page.locator('.sitenav a[aria-current=page]').isVisible(),true,'mobile sticky navigation');
    console.log('PASS: admin-only controls, CSRF, safe names, 2% thresholds, repeated/rebound/reload suppression, next day, stale quotes, all 6 indices/ETFs, exact index units, exclusion of ETF approximations/stale indices, ATH targets and boundary/rebound/new ATH/stale checks, sticky desktop/mobile navigation, dismiss, mobile.');
  }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(err=>{console.error(err);process.exitCode=1;});
