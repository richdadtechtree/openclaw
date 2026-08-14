#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pt_dashboard.py — PT 대시보드 웹앱
포트: 5001  |  DB: ~/pt_data/pt.db
실행: python3 pt_dashboard.py
"""
import sqlite3
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from flask import Flask, jsonify, render_template_string

DB_PATH = Path.home() / "pt_data" / "pt.db"
app = Flask(__name__)


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def db_query(sql, params=()):
    try:
        con = get_db()
        rows = con.execute(sql, params).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def db_one(sql, params=()):
    rows = db_query(sql, params)
    return rows[0] if rows else {}


HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>형준 PT 대시보드</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0d1117; --card: #161b22; --card2: #1c2128;
  --border: #30363d; --text: #e6edf3; --muted: #8b949e;
  --blue: #58a6ff; --green: #3fb950; --red: #f85149;
  --purple: #bc8cff; --orange: #d29922; --pink: #ff7b72;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; min-height: 100vh; }
.header { background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
  border-bottom: 1px solid var(--border); padding: 20px 32px;
  display: flex; align-items: center; justify-content: space-between; }
.header h1 { font-size: 22px; font-weight: 800; background: linear-gradient(90deg, var(--blue), var(--purple));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.header .subtitle { font-size: 13px; color: var(--muted); margin-top: 4px; }
.date-badge { background: var(--card2); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 14px; font-size: 13px; color: var(--muted); }
.tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border);
  padding: 0 32px; background: var(--card); }
.tab { padding: 14px 20px; font-size: 14px; font-weight: 500; color: var(--muted);
  cursor: pointer; border-bottom: 2px solid transparent; transition: all .2s; }
.tab.active { color: var(--blue); border-bottom-color: var(--blue); }
.tab:hover:not(.active) { color: var(--text); }
.panel { display: none; padding: 28px 32px; }
.panel.active { display: block; }
.grid4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
.card-title { font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase;
  letter-spacing: .8px; margin-bottom: 12px; }
.stat-num { font-size: 36px; font-weight: 800; line-height: 1; }
.stat-sub { font-size: 12px; color: var(--muted); margin-top: 6px; }
.badge { display: inline-block; padding: 3px 8px; border-radius: 20px; font-size: 11px; font-weight: 600; }
.badge-green { background: rgba(63,185,80,.15); color: var(--green); }
.badge-red { background: rgba(248,81,73,.15); color: var(--red); }
.badge-blue { background: rgba(88,166,255,.15); color: var(--blue); }
.badge-purple { background: rgba(188,140,255,.15); color: var(--purple); }
.badge-orange { background: rgba(210,153,34,.15); color: var(--orange); }
.section-title { font-size: 16px; font-weight: 700; margin-bottom: 16px;
  display: flex; align-items: center; gap: 8px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; font-size: 11px; font-weight: 600;
  color: var(--muted); text-transform: uppercase; letter-spacing: .6px;
  border-bottom: 1px solid var(--border); }
td { padding: 10px 12px; border-bottom: 1px solid rgba(48,54,61,.5); }
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--card2); }
.calendar { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
.cal-day { aspect-ratio: 1; border-radius: 6px; display: flex; align-items: center;
  justify-content: center; font-size: 12px; font-weight: 500; cursor: default;
  transition: transform .15s; }
.cal-day:hover { transform: scale(1.1); }
.cal-empty { background: transparent; }
.cal-rest { background: var(--card2); color: var(--muted); }
.cal-workout { background: linear-gradient(135deg, rgba(88,166,255,.3), rgba(188,140,255,.3));
  color: var(--blue); border: 1px solid rgba(88,166,255,.4); }
.cal-today { box-shadow: 0 0 0 2px var(--blue); }
.progress-bar { height: 6px; background: var(--card2); border-radius: 3px; overflow: hidden; margin-top: 8px; }
.progress-fill { height: 100%; border-radius: 3px;
  background: linear-gradient(90deg, var(--blue), var(--purple)); transition: width .5s; }
.ai-report { background: linear-gradient(135deg, rgba(88,166,255,.08), rgba(188,140,255,.08));
  border: 1px solid rgba(88,166,255,.2); border-radius: 12px; padding: 20px; margin-bottom: 24px; }
.ai-report .label { font-size: 11px; font-weight: 600; color: var(--blue); text-transform: uppercase;
  letter-spacing: .8px; margin-bottom: 10px; }
.ai-report p { font-size: 14px; color: var(--text); line-height: 1.7; }
.challenge-card { background: linear-gradient(135deg, rgba(63,185,80,.1), rgba(88,166,255,.1));
  border: 1px solid rgba(63,185,80,.3); border-radius: 12px; padding: 20px; }
.streak-num { font-size: 48px; font-weight: 900; color: var(--green); line-height: 1; }
.empty-state { text-align: center; padding: 40px; color: var(--muted); font-size: 14px; }
@media (max-width: 768px) {
  .grid4 { grid-template-columns: 1fr 1fr; }
  .grid2 { grid-template-columns: 1fr; }
  .panel { padding: 16px; }
}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🏋️ 형준 PT 대시보드</h1>
    <div class="subtitle">김종국 트레이너 · 실시간 기록</div>
  </div>
  <div class="date-badge" id="now-badge">--</div>
</div>
<div class="tabs">
  <div class="tab active" onclick="showTab('overview')">📊 오버뷰</div>
  <div class="tab" onclick="showTab('workouts')">💪 운동기록</div>
  <div class="tab" onclick="showTab('diet')">🥗 식단기록</div>
  <div class="tab" onclick="showTab('vitals')">⚖️ 체중&바이탈</div>
</div>

<!-- 오버뷰 -->
<div id="tab-overview" class="panel active">
  <div class="grid4" id="summary-cards">
    <div class="card"><div class="card-title">총 운동 기록</div>
      <div class="stat-num" id="total-workouts">-</div>
      <div class="stat-sub">운동 종목 누적</div></div>
    <div class="card"><div class="card-title">총 식단 기록</div>
      <div class="stat-num" id="total-diet">-</div>
      <div class="stat-sub">식사 기록 누적</div></div>
    <div class="card"><div class="card-title">바이탈 기록</div>
      <div class="stat-num" id="total-vitals">-</div>
      <div class="stat-sub">체중·수면 체크</div></div>
    <div class="card"><div class="card-title">최근 체중</div>
      <div class="stat-num" id="last-weight">-</div>
      <div class="stat-sub" id="weight-date">-</div></div>
  </div>

  <div class="grid2">
    <div class="challenge-card">
      <div class="card-title">🔥 연속 운동 챌린지</div>
      <div class="streak-num" id="streak">0</div>
      <div class="stat-sub" style="margin-top:8px">일 연속 달성</div>
      <div class="progress-bar" style="margin-top:16px">
        <div class="progress-fill" id="streak-bar" style="width:0%"></div>
      </div>
      <div class="stat-sub" style="margin-top:6px">목표: 30일</div>
    </div>
    <div class="card">
      <div class="card-title">📅 이번 달 운동 달력</div>
      <div class="calendar" id="calendar"></div>
    </div>
  </div>

  <div class="ai-report" id="ai-report-block" style="display:none">
    <div class="label">🤖 AI 피드백 리포트</div>
    <p id="ai-report-text"></p>
  </div>

  <div class="card">
    <div class="section-title">📋 최근 운동 현황</div>
    <table>
      <thead><tr><th>날짜</th><th>운동</th><th>세트</th><th>횟수</th><th>무게</th></tr></thead>
      <tbody id="recent-workouts-body"></tbody>
    </table>
  </div>
</div>

<!-- 운동기록 -->
<div id="tab-workouts" class="panel">
  <div class="card">
    <div class="section-title">💪 전체 운동 기록</div>
    <table>
      <thead><tr><th>날짜</th><th>운동</th><th>세트</th><th>횟수</th><th>무게(kg)</th></tr></thead>
      <tbody id="all-workouts-body"></tbody>
    </table>
  </div>
</div>

<!-- 식단기록 -->
<div id="tab-diet" class="panel">
  <div class="card">
    <div class="section-title">🥗 식단 기록</div>
    <table>
      <thead><tr><th>날짜</th><th>식사</th><th>메뉴</th><th>단백질(g)</th></tr></thead>
      <tbody id="diet-body"></tbody>
    </table>
  </div>
</div>

<!-- 바이탈 -->
<div id="tab-vitals" class="panel">
  <div class="grid2">
    <div class="card">
      <div class="section-title">⚖️ 체중 기록</div>
      <table>
        <thead><tr><th>날짜</th><th>체중(kg)</th><th>수면(h)</th><th>컨디션</th></tr></thead>
        <tbody id="vitals-body"></tbody>
      </table>
    </div>
    <div class="card">
      <div class="card-title">수면 평균</div>
      <div class="stat-num" id="avg-sleep">-</div>
      <div class="stat-sub">시간 / 일</div>
      <div style="height:24px"></div>
      <div class="card-title">음주 횟수 (최근 30일)</div>
      <div class="stat-num" id="alcohol-count" style="color:var(--orange)">-</div>
      <div class="stat-sub">회</div>
    </div>
  </div>
</div>

<script>
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  event.target.classList.add('active');
}

async function loadData() {
  const r = await fetch('/api/summary');
  const d = await r.json();

  document.getElementById('total-workouts').textContent = d.total_workouts ?? 0;
  document.getElementById('total-diet').textContent = d.total_diet ?? 0;
  document.getElementById('total-vitals').textContent = d.total_vitals ?? 0;
  document.getElementById('last-weight').textContent = d.last_weight ? d.last_weight+'kg' : '-';
  document.getElementById('weight-date').textContent = d.weight_date ?? '';
  document.getElementById('streak').textContent = d.streak ?? 0;
  document.getElementById('streak-bar').style.width = Math.min((d.streak/30)*100, 100)+'%';

  if (d.ai_report) {
    document.getElementById('ai-report-block').style.display = 'block';
    document.getElementById('ai-report-text').textContent = d.ai_report;
  }

  // 달력
  const cal = document.getElementById('calendar');
  cal.innerHTML = '';
  const now = new Date();
  const y = now.getFullYear(), m = now.getMonth();
  const first = new Date(y, m, 1).getDay();
  const days = new Date(y, m+1, 0).getDate();
  const wdates = new Set(d.workout_dates || []);
  const today = now.getDate();
  ['일','월','화','수','목','금','토'].forEach(dn => {
    const h = document.createElement('div');
    h.style.cssText = 'font-size:10px;color:var(--muted);text-align:center;padding:4px 0;font-weight:600';
    h.textContent = dn; cal.appendChild(h);
  });
  for (let i=0;i<first;i++) {
    const e=document.createElement('div'); e.className='cal-day cal-empty'; cal.appendChild(e);
  }
  const monthStr = `${y}-${String(m+1).padStart(2,'0')}`;
  for (let i=1;i<=days;i++) {
    const ds = `${monthStr}-${String(i).padStart(2,'0')}`;
    const el=document.createElement('div');
    el.className='cal-day '+(wdates.has(ds)?'cal-workout':'cal-rest');
    if(i===today) el.classList.add('cal-today');
    el.textContent=i; cal.appendChild(el);
  }

  // 최근 운동
  const rb = document.getElementById('recent-workouts-body');
  (d.recent_workouts||[]).forEach(w => {
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${w.date}</td><td><strong>${w.exercise}</strong></td>
      <td><span class="badge badge-blue">${w.sets}세트</span></td>
      <td>${w.reps}회</td>
      <td>${w.weight_kg?w.weight_kg+'kg':'-'}</td>`;
    rb.appendChild(tr);
  });

  // 전체 운동
  const ab = document.getElementById('all-workouts-body');
  const wr = await fetch('/api/workouts'); const wd = await wr.json();
  wd.forEach(w => {
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${w.date}</td><td>${w.exercise}</td>
      <td>${w.sets}</td><td>${w.reps}</td>
      <td>${w.weight_kg??'-'}</td>`;
    ab.appendChild(tr);
  });

  // 식단
  const db2 = document.getElementById('diet-body');
  const dr = await fetch('/api/diet'); const dd = await dr.json();
  dd.forEach(d2 => {
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${d2.date}</td>
      <td>${d2.meal?`<span class="badge badge-green">${d2.meal}</span>`:'-'}</td>
      <td>${d2.items}</td><td>${d2.protein_g??'-'}</td>`;
    db2.appendChild(tr);
  });

  // 바이탈
  const vb = document.getElementById('vitals-body');
  const vr = await fetch('/api/vitals'); const vd = await vr.json();
  const condMap = {excellent:'최고',good:'좋음',fair:'보통',tired:'피곤',poor:'나쁨',terrible:'최악'};
  vd.forEach(v => {
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${v.date}</td>
      <td>${v.weight_kg?v.weight_kg+'kg':'-'}</td>
      <td>${v.sleep_hours??'-'}</td>
      <td>${condMap[v.condition]??'-'}${v.alcohol?'🍺':''}</td>`;
    vb.appendChild(tr);
  });

  if (vd.length) {
    const sleeps = vd.filter(v=>v.sleep_hours).map(v=>v.sleep_hours);
    const avg = sleeps.length ? (sleeps.reduce((a,b)=>a+b,0)/sleeps.length).toFixed(1) : '-';
    document.getElementById('avg-sleep').textContent = avg;
    const alc = vd.filter(v=>v.alcohol).length;
    document.getElementById('alcohol-count').textContent = alc;
  }
}

// 시계
function updateClock() {
  const now = new Date();
  const opts = {year:'numeric',month:'long',day:'numeric',weekday:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'};
  document.getElementById('now-badge').textContent = now.toLocaleString('ko-KR', opts);
}
updateClock(); setInterval(updateClock, 1000);
loadData();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/summary")
def api_summary():
    today = date.today().isoformat()
    month = today[:7]

    total_w = db_one("SELECT COUNT(*) as n FROM workouts")
    total_d = db_one("SELECT COUNT(*) as n FROM diet")
    total_v = db_one("SELECT COUNT(*) as n FROM vitals")
    last_vital = db_one("SELECT weight_kg, date FROM vitals WHERE weight_kg IS NOT NULL ORDER BY date DESC LIMIT 1")

    # 연속 운동 스트릭
    streak = 0
    rows = db_query("SELECT DISTINCT date FROM workouts ORDER BY date DESC")
    check = date.today()
    for r in rows:
        rd = date.fromisoformat(r['date'])
        if rd == check:
            streak += 1
            check -= timedelta(days=1)
        elif rd < check:
            break

    # 이번 달 운동 날짜
    wdates = [r['date'] for r in db_query(
        "SELECT DISTINCT date FROM workouts WHERE date LIKE ?", (f"{month}%",))]

    # 최근 운동 10개
    recent = db_query(
        "SELECT date, exercise, sets, reps, weight_kg FROM workouts ORDER BY date DESC, id DESC LIMIT 10")

    # AI 리포트
    report_row = db_one("SELECT report FROM ai_reports ORDER BY date DESC LIMIT 1")

    return jsonify({
        "total_workouts": total_w.get("n", 0),
        "total_diet": total_d.get("n", 0),
        "total_vitals": total_v.get("n", 0),
        "last_weight": last_vital.get("weight_kg"),
        "weight_date": last_vital.get("date", ""),
        "streak": streak,
        "workout_dates": wdates,
        "recent_workouts": recent,
        "ai_report": report_row.get("report") if report_row else None,
    })


@app.route("/api/workouts")
def api_workouts():
    return jsonify(db_query(
        "SELECT date, exercise, sets, reps, weight_kg FROM workouts ORDER BY date DESC, id DESC LIMIT 200"))


@app.route("/api/diet")
def api_diet():
    return jsonify(db_query(
        "SELECT date, meal, items, protein_g FROM diet ORDER BY date DESC, id DESC LIMIT 100"))


@app.route("/api/vitals")
def api_vitals():
    return jsonify(db_query(
        "SELECT date, weight_kg, sleep_hours, condition, alcohol FROM vitals ORDER BY date DESC LIMIT 60"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
