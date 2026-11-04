/**
 * test_viewer_edition.js — 신문 요약 화면 '📰 종이신문 / 🌐 온라인신문' 고르기 확인 (실제 Chromium) — 2026-10-27 사용자 요청
 *
 *   ① 처음엔 종이신문: 종이 요약 + 오디오 칸 + 사설 칸, 서버엔 edition 없이 묻는다
 *   ② 온라인신문을 누르면: edition=online 으로 다시 받아 온라인 요약만, 사설·원본 칸은 숨김
 *      오디오 칸은 온라인 브리핑으로 바뀌고(18시 먼저), 09시·18시 단추로 고른다 (2026-10-28)
 *   ③ 고른 것을 기억(새로고침해도 온라인) · 주소 ?edition=paper 가 우선
 *   ④ 온라인 요약이 없으면 '9시·18시' 안내
 *   ⑤ 폰 390px 에서 옆으로 안 넘친다
 *   ⑥ 온라인 머리글(기준 시각·기사 범위)과 '새 기사 없음' 상태 메시지가 글로 보이고 기사 칸이 안 깨진다 (2026-10-28)
 * 실행: npm i playwright && node scripts/test_viewer_edition.js
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || chromium.executablePath();
const D = '2026-10-27';
const PAPER = `[신문요약 1/1] ${D}\n\n1. 🔵 종이기사 제목가\n• 사진: 01\n• WHAT: 종이 기사 내용.\n• WHY: 기사에 원인 언급 없음.\n• HOW:\n• [확정] 종이 사실.\n• 원문: <https://n.news.naver.com/mnews/article/009/0000000001|매일경제>`;
const HEAD = '🕘 온라인 신문 · 2026-10-27 09:00 기준 (한국시간)\n기사 범위: 2026-10-26 21:00 ~ 2026-10-27 09:00';
const ONLINE = `[신문요약 1/1] ${D} 09시 온라인신문\n\n${HEAD}\n\n1. 🔵 온라인기사 제목나\n• WHAT: 온라인 기사 내용.\n• WHY: 기사에 원인 언급 없음.\n• HOW:\n• [확정] 온라인 사실.\n• 원문: <https://n.news.naver.com/mnews/article/015/0000000002|한국경제>`;
const ED = { ok: true, date: D, items: [{ title: '사설 제목', url: 'https://www.mk.co.kr/news/editorial/1', paras: ['문단.'] }] };
let onlineMsgs = [ONLINE];
let onlinePods = [{ ok: true, slot: '18', title: '저녁 온라인', bytes: 2048, url: '/api/news/podcast/audio?date=' + D + '&slot=18' },
                  { ok: true, slot: '09', title: '아침 온라인', bytes: 2048, url: '/api/news/podcast/audio?date=' + D + '&slot=09' }];
const asked = [];
const srv = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x'), p = u.pathname;
  const send = (t, b) => { res.writeHead(200, { 'Content-Type': t }); res.end(b); };
  if (p === '/economy') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (p === '/economy/data') {
    const ed = u.searchParams.get('edition') || ''; asked.push(ed);
    const texts = ed === 'online' ? onlineMsgs : [PAPER];
    return send('application/json', JSON.stringify({ date: D, messages: texts.map(t => ({ ts: D + 'T09:05:00+09:00', source: 'web', kind: 'text', text: t })) }));
  }
  if (p === '/api/news/editorial') return send('application/json', JSON.stringify(ED));
  if (p === '/api/news/podcast') return send('application/json', JSON.stringify(u.searchParams.get('edition') === 'online'
    ? { ok: onlinePods.length > 0, date: D, items: onlinePods }
    : { ok: true, date: D, title: '오늘 브리핑', bytes: 2048, url: '/api/news/podcast/audio?date=' + D }));
  if (p === '/api/news/today') return send('application/json', JSON.stringify({ ok: true, ready: false, date: D }));
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true, checks = 0;
  const check = (ok, msg, extra = '') => { checks++; pass &&= ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const look = page => page.evaluate(() => {
    const vis = id => { const el = document.getElementById(id); return !!el && !el.hidden && el.getBoundingClientRect().height > 0; };
    return { feed: document.getElementById('feed').textContent, pod: vis('pod'), ed: vis('mk-ed'),
      podSrc: document.getElementById('pod-audio').getAttribute('src') || '', podSub: document.getElementById('pod-sub').textContent,
      slots: [...document.querySelectorAll('#pod-slots button')].map(b => b.textContent + (b.getAttribute('aria-pressed') === 'true' ? '*' : '')),
      pressed: document.querySelector('#edtog [aria-pressed="true"]').dataset.ed, label: document.getElementById('ed-label').textContent };
  });

  console.log('\n[① 처음엔 종이신문]');
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await ctx.route('https://**/*',r=>r.abort());
  let page = await ctx.newPage();
  await page.goto(base + '/economy');
  await page.waitForSelector('#mk-ed:not([hidden])');
  await page.waitForSelector('#pod:not([hidden])');
  let s = await look(page);
  check(s.pressed === 'paper' && /종이기사 제목가/.test(s.feed) && !/온라인기사/.test(s.feed), '종이 요약이 보이고 종이신문 단추가 눌림', s.label);
  check(s.pod && s.ed, '오디오 칸·사설 칸이 보인다');
  check(asked[0] === '', '서버엔 edition 없이 묻는다(기존 그대로)', JSON.stringify(asked));

  console.log('\n[② 온라인신문 누르기]');
  await page.click('#edtog button[data-ed="online"]');
  await page.waitForFunction(() => /온라인기사 제목나/.test(document.getElementById('feed').textContent));
  s = await look(page);
  check(!/종이기사/.test(s.feed), '온라인 요약만 보인다');
  check(!s.ed && await page.evaluate(() => document.getElementById('news').hidden), '사설·원본 칸은 숨김');
  await page.waitForFunction(() => /slot=18/.test(document.getElementById('pod-audio').getAttribute('src') || ''));
  s = await look(page);
  check(s.pod && /18시 · 저녁 온라인/.test(s.podSub) && s.slots.join() === '09시,18시*', '오디오 칸은 온라인 18시 브리핑, 09시·18시 단추', `${s.podSub} [${s.slots}]`);
  await page.click('#pod-slots button[data-slot="09"]');
  s = await look(page);
  check(/slot=09/.test(s.podSrc) && /09시 · 아침 온라인/.test(s.podSub) && s.slots.join() === '09시*,18시', '09시 단추를 누르면 아침 브리핑으로', s.podSrc);
  check(s.pressed === 'online' && /온라인/.test(s.label) && asked.includes('online'), '단추·제목 줄이 온라인으로, 서버엔 edition=online', s.label);
  await page.click('#edtog button[data-ed="paper"]');
  await page.waitForFunction(() => /종이기사 제목가/.test(document.getElementById('feed').textContent));
  await page.waitForSelector('#mk-ed:not([hidden])');
  await page.waitForSelector('#pod:not([hidden])');
  await page.waitForFunction(() => /audio\?date=[\d-]+$/.test(document.getElementById('pod-audio').getAttribute('src') || ''));
  s = await look(page);
  check(s.slots.length === 0 && /오늘 브리핑/.test(s.podSub), '종이신문으로 돌아오면 종이 오디오·사설 칸이 다시 보인다', s.podSub);
  await page.click('#edtog button[data-ed="online"]');
  await page.waitForFunction(() => /온라인기사/.test(document.getElementById('feed').textContent));

  console.log('\n[③ 기억하기]');
  await page.reload();
  await page.waitForFunction(() => /온라인기사 제목나/.test(document.getElementById('feed').textContent));
  check((await look(page)).pressed === 'online', '새로고침해도 온라인신문');
  await page.goto(base + '/economy?edition=paper');
  await page.waitForFunction(() => /종이기사 제목가/.test(document.getElementById('feed').textContent));
  check((await look(page)).pressed === 'paper', '주소 ?edition=paper 가 기억보다 우선');
  await page.close();

  console.log('\n[④ 온라인 요약이 없을 때]');
  onlineMsgs = [];
  onlinePods = [onlinePods[1]];
  page = await ctx.newPage();
  await page.goto(base + '/economy?edition=online');
  await page.waitForSelector('#feed .empty');
  check(/9시·18시/.test(await page.textContent('#feed .empty')), "'9시·18시에 올립니다' 안내");
  await page.waitForSelector('#pod:not([hidden])');
  s = await look(page);
  check(/slot=09/.test(s.podSrc) && s.slots.length === 0, '온라인 오디오가 하나면 시간대 단추 없이 그것만', s.podSub);
  await page.close(); await ctx.close();

  console.log('\n[⑤ 폰]');
  onlineMsgs = [ONLINE];
  page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await page.route('https://**/*',r=>r.abort());
  await page.goto(base + '/economy?edition=online');
  await page.waitForFunction(() => /온라인기사/.test(document.getElementById('feed').textContent));
  const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  const tg = await page.evaluate(() => { const r = document.getElementById('edtog').getBoundingClientRect(); return { l: r.left, r: r.right }; });
  check(over <= 0 && tg.l >= 0 && tg.r <= 390, '폰에서 옆으로 안 넘치고 단추가 화면 안에', `넘침 ${over}px · ${Math.round(tg.l)}~${Math.round(tg.r)}`);
  await page.close();

  console.log('\n[⑥ 머리글·상태 메시지]');
  page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.route('https://**/*',r=>r.abort());
  await page.goto(base + '/economy?edition=online');
  await page.waitForFunction(() => /온라인기사 제목나/.test(document.getElementById('feed').textContent));
  let f = await page.evaluate(() => document.getElementById('feed').innerText);
  check(/09:00 기준 \(한국시간\)/.test(f) && /기사 범위: 2026-10-26 21:00 ~ 2026-10-27 09:00/.test(f), '머리글이 보인다');
  check(/온라인기사 제목나/.test(f) && /온라인 사실/.test(f) && f.indexOf('기사 범위') < f.indexOf('온라인기사 제목나'), '머리글 뒤 기사 칸이 그대로');
  onlineMsgs = [`[신문요약 1/1] ${D} 18시 온라인신문\n\n${HEAD.replace('09:00 기준', '18:00 기준')}\n\n최근 12시간 내 새 기사 없음\n\n\`\`\`json\n{"status":"empty","articles":[]}\n\`\`\``];
  await page.reload();
  await page.waitForFunction(() => /새 기사 없음/.test(document.getElementById('feed').textContent));
  f = await page.evaluate(() => document.getElementById('feed').innerText);
  check(/최근 12시간 내 새 기사 없음/.test(f) && !/"status"/.test(f), "'최근 12시간 내 새 기사 없음' 상태 메시지(JSON 꼬리는 숨김)", f.slice(0, 120).replace(/\n/g, ' / '));

  await page.close();


  console.log('\n[⑦ 온라인 시간대별 바로 이동]');
  const MORNING = ONLINE.replace('온라인 기사 내용.', '오전 기사 본문입니다. '.repeat(130));
  const EVENING = MORNING.replaceAll('09시 온라인신문','18시 온라인신문').replaceAll('09:00 기준','18:00 기준').replaceAll('온라인기사 제목나','저녁기사 제목다');
  onlineMsgs = [MORNING, MORNING.replace('1/1','2/2'), EVENING];
  page = await browser.newPage({viewport:{width:1280,height:900}});
  await page.route('https://**/*',r=>r.abort());
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/economy?edition=online');
  await page.waitForSelector('#online-news-09');
  await page.waitForSelector('#online-news-18');
  await page.waitForFunction(()=>[...document.querySelectorAll('#section-jump button')].every(b=>!b.disabled));
  const labels=()=>page.evaluate(()=>[...document.querySelectorAll('#section-jump button')].map(b=>b.lastElementChild.textContent).join('|'));
  check(await labels()==='브리핑|9시 뉴스|18시 뉴스|커스터마이징','온라인에서는 브리핑·9시 뉴스·18시 뉴스');
  check(await page.locator('#online-news-09').count()===1,'9시 요약이 여러 메시지여도 이동 지점은 하나');
  check((await page.locator('#online-news-18').textContent()).includes('저녁기사 제목다'),'게시 시각이 9시여도 머리글 18시 뉴스로 분류');
  await page.evaluate(()=>{
    window.__jumpCalls=[];const original=window.scrollTo;
    window.scrollTo=function(options){window.__jumpCalls.push(options);return original.call(window,options);};
  });
  for(const id of ['online-news-18','online-news-09']){
    await page.click('#section-jump [data-section="'+id+'"]');
    const result=await page.evaluate(id=>{
      const top=document.getElementById(id).getBoundingClientRect().top;
      const offset=document.querySelector('.sitenav').getBoundingClientRect().height+document.getElementById('toolbar').getBoundingClientRect().height+16;
      return {top,offset,selected:document.querySelector('#section-jump [aria-current=location]')?.dataset.section};
    },id);
    check(Math.abs(result.top-result.offset)<2&&result.selected===id,id+' 누르면 상단 메뉴 아래로 즉시 이동',JSON.stringify(result));
  }
  check(await page.evaluate(()=>window.__jumpCalls.length===2&&window.__jumpCalls.every(c=>c.behavior==='instant')),'스크롤 애니메이션 없음');
  await page.click('#section-jump [data-section=pod]');
  check(await page.evaluate(()=>document.getElementById('pod').getBoundingClientRect().top>=0),'브리핑 버튼은 오디오 칸으로 이동');
  onlineMsgs=[MORNING];
  await page.reload();
  await page.waitForFunction(()=>!document.querySelector('#section-jump [data-section="online-news-09"]').disabled);
  check(await page.locator('#section-jump [data-section="online-news-18"]').isDisabled(),'18시 뉴스가 없으면 해당 버튼 비활성');
  check(await page.locator('#online-news-18').count()===0,'없는 시간대로 잘못 이동하지 않음');
  onlineMsgs=[];
  await page.reload();
  await page.waitForSelector('#feed .empty');
  await page.waitForFunction(()=>document.querySelector('#section-jump [data-section="online-news-09"]').disabled);
  check(await page.locator('#section-jump [data-section="online-news-18"]').isDisabled(),'뉴스가 없으면 두 시간대 모두 비활성');
  await page.click('#edtog [data-ed=paper]');
  await page.waitForFunction(()=>document.getElementById('section-jump').dataset.edition==='paper');
  check(await labels()==='오디오 브리핑|기사요약|사설|커스터마이징','종이신문으로 돌아가면 기존 메뉴 복원');
  check(errors.length===0,'온라인 이동 중 자바스크립트 오류 없음',errors.join(','));
  await page.close();
  onlineMsgs=[MORNING,EVENING];
  page=await browser.newPage({viewport:{width:390,height:844}});
  await page.route('https://**/*',r=>r.abort());
  await page.goto(base+'/economy?edition=online');
  await page.waitForSelector('#online-news-18');
  await page.click('#section-jump [data-section="online-news-18"]');
  const mobile=await page.evaluate(()=>{
    const nav=document.getElementById('section-jump').getBoundingClientRect();
    const target=document.getElementById('online-news-18').getBoundingClientRect();
    return {overflow:document.documentElement.scrollWidth-innerWidth,left:nav.left,right:nav.right,top:target.top};
  });
  check(mobile.overflow<=0&&mobile.left>=0&&mobile.right<=390,'모바일에서도 버튼 세 개가 화면 안에 표시',JSON.stringify(mobile));
  check(mobile.top>=0&&mobile.top<844,'모바일 18시 뉴스 이동');
  await page.close();

  await browser.close(); srv.close();
  console.log('\n총평: ' + (pass ? '✅ 전부 통과' : '❌ 실패 있음'));
  if(pass)console.log('PASS: '+checks+' edition and online navigation browser checks');
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error(e); srv.close(); process.exit(1); });
