/**
 * test_viewer_redo.js — 관리자 전용 '🔁 다시 가져와 요약' 버튼 화면 확인 (실제 Chromium, 가짜 서버) — 2026-11-09 사용자 요청
 *   ① 관리자가 아니면(서버 403) 버튼도 상태 칸도 안 보임
 *   ② 관리자는 버튼이 보이고, 누르면 확인창(취소하면 아무것도 안 보냄) → 서버에 시작 요청
 *   ③ 진행 중엔 버튼이 꺼지고 단계(가져오기·연결·요약 요청)가 ⏳/✅ 로 보임, 끝나면 사진 목록을 다시 불러옴
 *   ④ 실패하면 ❌ + 이유 + 로그 끝부분, 어제 결과는 오늘 화면에 안 남음, 폰 390px 에서 넘치지 않음
 * 실행: node scripts/test_viewer_redo.js   (개발 환경 전용)
 */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), zlib = require('zlib');
const HTML = path.join(__dirname, '..', 'stock', 'slack_digest_live.html');
const CHROME = process.env.PW_CHROME || chromium.executablePath();

function makePng(w, h) {
  const crc32 = (buf) => { let c, crc = 0xffffffff;
    for (let n = 0; n < buf.length; n++) { c = (crc ^ buf[n]) & 0xff;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = c ^ (crc >>> 8); }
    return (crc ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => { const tc = Buffer.concat([Buffer.from(type), data]);
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(tc));
    return Buffer.concat([len, tc, crc]); };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(w * 3, 235)]);
  const raw = Buffer.concat(Array.from({ length: h }, () => row));
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}
const PNG = makePng(800, 1200);
const BRIEF = ['*[신문요약 1/1] 신문 요약*', '1. 기사 제목\n• WHAT: 내용임.\n• WHY: 이유임.\n• HOW: 방법임.\n• 사진: 03'].join('\n');
let ADMIN = true, MODE = 'idle', todayHits = 0, posts = 0, polls = 0, FINISHED_DATE = null, lastMode = null;
const STEPS = (a, b, c) => ({ collect: { status: a, note: '' }, sync: { status: b, note: '' }, summary: { status: c, note: '' } });
const stateOf = () => {
  const base = { labels: { collect: '카페에서 다시 가져오기', sync: '웹에 연결', summary: '기사 요약' }, can_summary: true, tail: '', date: FINISHED_DATE || '' };
  if (MODE === 'idle') return Object.assign(base, { running: false, ok: null, finished: 0, message: '', steps: {} });
  if (MODE === 'running') { polls++; return Object.assign(base, { running: true, ok: null, finished: 0, message: '', steps: polls < 3 ? STEPS('run', 'wait', 'wait') : STEPS('ok', 'run', 'wait') }); }
  if (MODE === 'done') return Object.assign(base, { running: false, ok: true, finished: 1, message: '30쪽 · 90개 기사 요약을 완료했어요.', steps: STEPS('ok', 'ok', 'ok') });
  if (MODE === 'fail') return Object.assign(base, { running: false, ok: false, finished: 1, message: '카페에서 오늘 신문 글을 아직 못 찾았거나 받기에 실패했어요.', tail: '글을 찾지 못했습니다 (로그 끝)', steps: STEPS('fail', 'wait', 'wait') });
};
let D0 = '2026-11-09';
const srv = http.createServer((req, res) => {
  const u = req.url.split('?')[0];
  const D = new URL(req.url, 'http://x').searchParams.get('date') || D0;
  const send = (t, b, code = 200) => { res.writeHead(code, { 'Content-Type': t }); res.end(b); };
  const json = (o, code = 200) => send('application/json', JSON.stringify(o), code);
  if (u === '/' || u === '/economy') return send('text/html; charset=utf-8', fs.readFileSync(HTML));
  if (u === '/economy/data') return json({ date: D, messages: [{ ts: D + 'T06:29:00', source: 'user', kind: 'text', text: BRIEF }] });
  if (u === '/api/news/today') {
    todayHits++;
    const images = Array.from({ length: 6 }, (_, i) => { const n = String(i + 1).padStart(2, '0') + '.jpg'; return { name: n, url: '/page.png?n=' + n, thumb: '/page.png?t=' + n, download_url: '/page.png' }; });
    return json({ ok: true, ready: true, date: D, count: 6, images });
  }
  if (u === '/api/news/redo' && req.method === 'GET') return ADMIN ? json({ ok: true, state: stateOf() }) : json({ ok: false }, 403);
  if (u === '/api/news/redo' && req.method === 'POST') {
    let b = ''; req.on('data', c => b += c); req.on('end', () => { posts++; lastMode = JSON.parse(b).mode; polls = 0; MODE = 'running'; setTimeout(() => { MODE = process.env.__END || 'done'; }, 1500); json({ ok: true, started: true, state: stateOf() }); });
    return;
  }
  if (u === '/api/news/terms') return json({ ok: false }, 403);
  if (u === '/api/news/pagetext') return json({ ok: false });
  if (u === '/page.png') return send('image/png', PNG);
  res.writeHead(404); res.end();
});

(async () => {
  await new Promise(r => srv.listen(0, r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await chromium.launch({ executablePath: CHROME });
  let pass = true;
  const check = (ok, msg, extra = '') => { pass &&= !!ok; console.log((ok ? '  ✅ ' : '  ❌ ') + msg + (extra ? `  ${extra}` : '')); };
  const newPage = async (opts = {}) => {
    const ctx = await browser.newContext(Object.assign({ viewport: { width: 1280, height: 860 } }, opts));
    const page = await ctx.newPage();
    page.on('pageerror', e => { pass = false; console.log('  ❌ 페이지 오류: ' + e.message); });
    await page.goto(base + '/economy');
    await page.waitForFunction(() => document.getElementById('news') && !document.getElementById('news').hidden);
    await page.waitForTimeout(400);
    return { ctx, page };
  };
  const today = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);

  console.log('\n[① 관리자가 아니면]');
  ADMIN = false; MODE = 'idle';
  let { ctx, page } = await newPage();
  for(const id of ['news-redo','news-download','news-summary']) check(await page.$eval('#'+id, b => b.hidden), id+' 일반 회원에게 숨김');
  check(await page.$eval('#redo-status', b => b.hidden), '상태 칸도 안 보임');
  await ctx.close();

  console.log('\n[② 관리자: 확인창]');
  ADMIN = true; MODE = 'idle'; posts = 0; FINISHED_DATE = today();
  ({ ctx, page } = await newPage());
  check(!(await page.$eval('#news-redo', b => b.hidden)), '버튼이 보임');
  check(await page.$eval('#redo-status', b => b.hidden), '아직 한 적 없으면 상태 칸은 숨김');
  let msg = '';
  page.once('dialog', d => { msg = d.message(); d.dismiss(); });
  await page.click('#news-redo'); await page.waitForTimeout(400);
  check(posts === 0, '확인창에서 취소하면 서버에 아무것도 안 보냄', msg.split('\n')[0]);
  check(/전체 지면 요약/.test(msg), '확인창이 하는 일(전체 지면 요약)을 알려 줌');

  console.log('\n[③ 진행 → 완료]');
  page.once('dialog', d => d.accept());
  const before = todayHits;
  await page.click('#news-redo');
  await page.waitForFunction(() => document.getElementById('news-redo').disabled);
  check(posts === 1 && lastMode === 'all', '다운로드·요약 모드 요청 1번');
  check(await page.$eval('#news-summary', b => b.disabled) && await page.$eval('#news-download', b => b.disabled), '실행 중 모든 버튼 비활성화');
  check((await page.$eval('#news-redo', b => b.textContent)).includes('진행 중'), '진행 중에는 버튼이 꺼지고 "진행 중" 표시');
  await page.waitForFunction(() => /⏳|✅/.test(document.getElementById('redo-status').textContent));
  check(!(await page.$eval('#redo-status', b => b.hidden)), '단계 상태 칸이 보임');
  await page.waitForFunction(() => /90개 기사/.test(document.getElementById('redo-status').textContent), null, { timeout: 15000 });
  const txt = await page.$eval('#redo-status', b => b.textContent);
  check(/✅ 카페에서 다시 가져오기/.test(txt) && /✅ 웹에 연결/.test(txt) && /✅ 기사 요약/.test(txt), '세 단계가 모두 ✅', txt.replace(/\s+/g, ' ').slice(0, 90));
  await page.waitForTimeout(600);
  check(!(await page.$eval('#news-redo', b => b.disabled)), '끝나면 버튼이 다시 켜짐');
  check(todayHits > before + 0, '끝나면 사진 목록을 다시 불러옴', `${before}→${todayHits}`);
  check((await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)), '가로로 넘치지 않음(PC)');
  await ctx.close();

  console.log('\n[④ 다운로드만 / 요약만]');
  MODE='idle';
  ({ ctx, page } = await newPage());
  page.once('dialog', d => d.accept());
  await page.click('#news-download');
  await page.waitForFunction(() => document.getElementById('news-download').disabled);
  check(lastMode === 'download', '다운로드만 모드 전송');
  await page.waitForFunction(() => !document.getElementById('news-download').disabled, null, {timeout:15000});
  page.once('dialog', d => d.accept());
  await page.click('#news-summary');
  await page.waitForFunction(() => document.getElementById('news-summary').disabled);
  check(lastMode === 'summary', '이미 받은 파일 요약 모드 전송');
  await page.waitForFunction(() => !document.getElementById('news-summary').disabled, null, {timeout:15000});
  await ctx.close();
  console.log('\n[⑤ 실패·옛 결과·폰]');
  process.env.__END = 'fail'; posts = 0; MODE = 'idle'; FINISHED_DATE = today();
  ({ ctx, page } = await newPage({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true }));
  page.once('dialog', d => d.accept());
  await page.tap('#news-redo');
  await page.waitForFunction(() => /❌/.test(document.getElementById('redo-status').textContent), null, { timeout: 15000 });
  const f = await page.$eval('#redo-status', b => b.textContent);
  check(/못 찾았거나/.test(f) && /로그 끝/.test(f), '실패하면 ❌ + 이유 + 로그 끝부분', f.replace(/\s+/g, ' ').slice(0, 80));
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '폰 390px 에서 가로로 안 넘침');
  const r = await page.$eval('#news-redo', b => { const q = b.getBoundingClientRect(); return { l: q.left, r: q.right, vw: innerWidth }; });
  check(r.l >= 0 && r.r <= r.vw, '폰에서 버튼이 화면 안', JSON.stringify(r));
  for(const id of ['news-download','news-summary']) check(await page.$eval('#'+id, b => {const r=b.getBoundingClientRect(); return r.left>=0 && r.right<=innerWidth;}), id+' 폰 화면 안');
  await ctx.close();

  MODE = 'fail'; FINISHED_DATE = '2000-01-01';
  ({ ctx, page } = await newPage());
  check(await page.$eval('#redo-status', b => b.hidden), '어제(다른 날) 결과는 오늘 화면에 안 남음');
  await ctx.close();

  await browser.close(); srv.close();
  console.log(pass ? '\n✅ 모두 통과' : '\n❌ 실패 있음');
  process.exit(pass ? 0 : 1);
})();
