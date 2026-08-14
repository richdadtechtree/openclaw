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
from flask import Flask, jsonify, render_template_string, request

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


def ensure_tables():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS workouts (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, exercise TEXT NOT NULL, sets INTEGER, reps INTEGER, weight_kg REAL, raw TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS diet (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, meal TEXT, items TEXT NOT NULL, protein_g REAL, raw TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS vitals (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL UNIQUE, weight_kg REAL, sleep_hours REAL, condition TEXT, alcohol INTEGER DEFAULT 0, raw TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS briefings (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, type TEXT NOT NULL DEFAULT 'daily', content TEXT NOT NULL, created_at TEXT NOT NULL);
    """)
    con.commit(); con.close()

ensure_tables()

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
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
.btn-add { margin-left: auto; background: var(--blue); color: #000; border: none; border-radius: 6px;
  padding: 6px 14px; font-size: 12px; font-weight: 700; cursor: pointer; transition: opacity .2s; }
.btn-add:hover { opacity: .8; }
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.7);
  z-index: 1000; align-items: center; justify-content: center; }
.modal-overlay.open { display: flex; }
.modal { background: var(--card); border: 1px solid var(--border); border-radius: 16px;
  padding: 28px; width: 420px; max-width: 95vw; }
.modal h3 { font-size: 18px; font-weight: 700; margin-bottom: 20px; }
.form-row { margin-bottom: 14px; }
.form-row label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; font-weight: 600; }
.form-row input, .form-row select, .form-row textarea {
  width: 100%; background: var(--card2); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text); padding: 10px 12px; font-size: 14px; outline: none; font-family: inherit; }
.form-row input:focus, .form-row select:focus, .form-row textarea:focus { border-color: var(--blue); }
.form-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.btn-submit { width: 100%; background: linear-gradient(90deg, var(--blue), var(--purple));
  color: #fff; border: none; border-radius: 8px; padding: 12px; font-size: 15px;
  font-weight: 700; cursor: pointer; margin-top: 8px; }
.btn-submit:hover { opacity: .9; }
.btn-cancel { background: none; border: 1px solid var(--border); border-radius: 8px;
  color: var(--muted); padding: 10px; font-size: 14px; cursor: pointer; width: 100%; margin-top: 8px; }
.briefing-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
  padding: 18px; margin-bottom: 12px; }
.briefing-type { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; margin-bottom: 8px; }
.briefing-content { font-size: 14px; line-height: 1.7; white-space: pre-wrap; color: var(--text); }
.briefing-date { font-size: 11px; color: var(--muted); margin-top: 8px; }
.btn-del { background: none; border: none; cursor: pointer; opacity: .4; font-size: 14px; padding: 2px 6px; border-radius: 4px; transition: all .2s; }
.btn-del:hover { opacity: 1; color: var(--red); background: rgba(248,81,73,.15); }
.btn-edit { background: none; border: none; cursor: pointer; opacity: .4; font-size: 14px; padding: 2px 6px; border-radius: 4px; transition: all .2s; margin-right: 2px; }
.btn-edit:hover { opacity: 1; color: var(--blue); background: rgba(88,166,255,.15); }
@media (max-width: 768px) {
  .grid4 { grid-template-columns: 1fr 1fr; }
  .grid3 { grid-template-columns: 1fr; }
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

  <div class="grid3">
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
      <div class="card-title">🏆 풀업 최고 기록</div>
      <div class="stat-num" style="color:var(--purple)" id="pullup-pr">-</div>
      <div class="stat-sub" id="pullup-pr-date">개 (날짜 미확인)</div>
      <div style="height:12px"></div>
      <div class="card-title">오늘</div>
      <div class="stat-num" style="font-size:28px" id="pullup-today">-</div>
      <div class="stat-sub">개</div>
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

  <div id="briefings-section">
    <div class="section-title" style="margin-bottom:12px">📢 김종국 브리핑</div>
    <div id="briefings-list"></div>
  </div>

  <div class="card" style="margin-top:24px">
    <div class="section-title">📋 최근 운동 현황</div>
    <table>
      <thead><tr><th>날짜</th><th>운동</th><th>세트</th><th>횟수</th><th>무게</th><th>관리</th></tr></thead>
      <tbody id="recent-workouts-body"></tbody>
    </table>
  </div>
</div>

<!-- 운동기록 -->
<div id="tab-workouts" class="panel">
  <div class="card">
    <div class="section-title">💪 전체 운동 기록
      <button class="btn-add" onclick="openModal('workout')">+ 추가</button>
    </div>
    <table>
      <thead><tr><th>날짜</th><th>운동</th><th>세트</th><th>횟수</th><th>무게(kg)</th><th>관리</th></tr></thead>
      <tbody id="all-workouts-body"></tbody>
    </table>
  </div>
</div>

<!-- 식단기록 -->
<div id="tab-diet" class="panel">
  <div class="card">
    <div class="section-title">🥗 식단 기록
      <button class="btn-add" onclick="openModal('diet')">+ 추가</button>
    </div>
    <table>
      <thead><tr><th>날짜</th><th>식사</th><th>메뉴</th><th>단백질(g)</th><th>관리</th></tr></thead>
      <tbody id="diet-body"></tbody>
    </table>
  </div>
</div>

<!-- 바이탈 -->
<div id="tab-vitals" class="panel">
  <div class="grid2">
    <div class="card">
      <div class="section-title">⚖️ 체중 기록
        <button class="btn-add" onclick="openModal('vital')">+ 추가</button>
      </div>
      <table>
        <thead><tr><th>날짜</th><th>체중(kg)</th><th>수면(h)</th><th>컨디션</th><th>관리</th></tr></thead>
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

  // 캐시 객체
  window.cacheWorkouts = {}; window.cacheDiet = {}; window.cacheVitals = {};

  // 최근 운동
  const rb = document.getElementById('recent-workouts-body');
  (d.recent_workouts||[]).forEach(w => {
    window.cacheWorkouts[w.id] = w;
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${w.date}</td><td><strong>${w.exercise}</strong></td>
      <td><span class="badge badge-blue">${w.sets}세트</span></td>
      <td>${w.reps}회</td>
      <td>${w.weight_kg?w.weight_kg+'kg':'-'}</td>
      <td><button class="btn-edit" onclick="openEditModal('workout',${w.id})">✏️</button><button class="btn-del" onclick="deleteRecord('workout',${w.id})">🗑️</button></td>`;
    rb.appendChild(tr);
  });

  // 전체 운동
  const ab = document.getElementById('all-workouts-body');
  const wr = await fetch('/api/workouts'); const wd = await wr.json();
  wd.forEach(w => {
    window.cacheWorkouts[w.id] = w;
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${w.date}</td><td>${w.exercise}</td>
      <td>${w.sets}</td><td>${w.reps}</td>
      <td>${w.weight_kg??'-'}</td>
      <td><button class="btn-edit" onclick="openEditModal('workout',${w.id})">✏️</button><button class="btn-del" onclick="deleteRecord('workout',${w.id})">🗑️</button></td>`;
    ab.appendChild(tr);
  });

  // 식단
  const db2 = document.getElementById('diet-body');
  const dr = await fetch('/api/diet'); const dd = await dr.json();
  dd.forEach(d2 => {
    window.cacheDiet[d2.id] = d2;
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${d2.date}</td>
      <td>${d2.meal?`<span class="badge badge-green">${d2.meal}</span>`:'-'}</td>
      <td>${d2.items}</td><td>${d2.protein_g??'-'}</td>
      <td><button class="btn-edit" onclick="openEditModal('diet',${d2.id})">✏️</button><button class="btn-del" onclick="deleteRecord('diet',${d2.id})">🗑️</button></td>`;
    db2.appendChild(tr);
  });

  // 바이탈
  const vb = document.getElementById('vitals-body');
  const vr = await fetch('/api/vitals'); const vd = await vr.json();
  const condMap = {excellent:'최고',good:'좋음',fair:'보통',tired:'피곤',poor:'나쁨',terrible:'최악'};
  vd.forEach(v => {
    window.cacheVitals[v.id] = v;
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${v.date}</td>
      <td>${v.weight_kg?v.weight_kg+'kg':'-'}</td>
      <td>${v.sleep_hours??'-'}</td>
      <td>${condMap[v.condition]??'-'}${v.alcohol?'🍺':''}</td>
      <td><button class="btn-edit" onclick="openEditModal('vital',${v.id})">✏️</button><button class="btn-del" onclick="deleteRecord('vital',${v.id})">🗑️</button></td>`;
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

// 모달
function openModal(type) {
  document.getElementById('modal-'+type).classList.add('open');
}
function closeModal(type) {
  document.getElementById('modal-'+type).classList.remove('open');
}
async function submitForm(type, data) {
  const r = await fetch('/api/add/'+type, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if ((await r.json()).ok) { closeModal(type); location.reload(); }
  else alert('저장 실패');
}
async function deleteRecord(type, id) {
  if (!confirm('정말 이 기록을 삭제하시겠습니까?')) return;
  const r = await fetch('/api/delete/' + type + '/' + id, {method: 'POST'});
  if ((await r.json()).ok) location.reload();
  else alert('삭제 실패');
}

// 수정 모달 제어
function openEditModal(type, id) {
  if (type === 'workout') {
    const w = window.cacheWorkouts[id]; if (!w) return;
    document.getElementById('ew-id').value = w.id;
    document.getElementById('ew-date').value = w.date;
    document.getElementById('ew-exercise').value = w.exercise || '';
    document.getElementById('ew-sets').value = w.sets ?? 1;
    document.getElementById('ew-reps').value = w.reps ?? 1;
    document.getElementById('ew-weight').value = w.weight_kg ?? '';
    document.getElementById('modal-edit-workout').classList.add('open');
  } else if (type === 'diet') {
    const d = window.cacheDiet[id]; if (!d) return;
    document.getElementById('ed-id').value = d.id;
    document.getElementById('ed-date').value = d.date;
    document.getElementById('ed-meal').value = d.meal || '';
    document.getElementById('ed-items').value = d.items || '';
    document.getElementById('ed-protein').value = d.protein_g ?? '';
    document.getElementById('modal-edit-diet').classList.add('open');
  } else if (type === 'vital') {
    const v = window.cacheVitals[id]; if (!v) return;
    document.getElementById('ev-id').value = v.id;
    document.getElementById('ev-date').value = v.date;
    document.getElementById('ev-weight').value = v.weight_kg ?? '';
    document.getElementById('ev-sleep').value = v.sleep_hours ?? '';
    document.getElementById('ev-cond').value = v.condition || '';
    document.getElementById('ev-alcohol').value = v.alcohol ?? 0;
    document.getElementById('modal-edit-vital').classList.add('open');
  }
}
function closeEditModal(type) {
  document.getElementById('modal-edit-' + type).classList.remove('open');
}
async function submitEditForm(type) {
  let id, data;
  if (type === 'workout') {
    id = document.getElementById('ew-id').value;
    data = {
      date: document.getElementById('ew-date').value,
      exercise: document.getElementById('ew-exercise').value,
      sets: document.getElementById('ew-sets').value,
      reps: document.getElementById('ew-reps').value,
      weight_kg: document.getElementById('ew-weight').value || null
    };
  } else if (type === 'diet') {
    id = document.getElementById('ed-id').value;
    data = {
      date: document.getElementById('ed-date').value,
      meal: document.getElementById('ed-meal').value || null,
      items: document.getElementById('ed-items').value,
      protein_g: document.getElementById('ed-protein').value || null
    };
  } else if (type === 'vital') {
    id = document.getElementById('ev-id').value;
    data = {
      date: document.getElementById('ev-date').value,
      weight_kg: document.getElementById('ev-weight').value || null,
      sleep_hours: document.getElementById('ev-sleep').value || null,
      condition: document.getElementById('ev-cond').value || null,
      alcohol: document.getElementById('ev-alcohol').value
    };
  }
  const r = await fetch('/api/edit/' + type + '/' + id, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  if ((await r.json()).ok) { closeEditModal(type); location.reload(); }
  else alert('수정 실패');
}

// 풀업 PR 로드
async function loadPullupPR() {
  const r = await fetch('/api/pullup-pr');
  const d = await r.json();
  document.getElementById('pullup-pr').textContent = d.pr ?? '-';
  document.getElementById('pullup-pr-date').textContent = d.pr ? `개 (${d.pr_date})` : '기록 없음';
  const today = new Date().toISOString().slice(0,10);
  const todayRow = (d.daily||[]).find(r=>r.date===today);
  document.getElementById('pullup-today').textContent = todayRow ? todayRow.max_reps : '-';
}

// 브리핑 로드
async function loadBriefings() {
  const r = await fetch('/api/briefings');
  const items = await r.json();
  const el = document.getElementById('briefings-list');
  if (!items.length) { el.innerHTML = '<div class="empty-state">브리핑이 없습니다</div>'; return; }
  el.innerHTML = items.map(b => `
    <div class="briefing-card">
      <div class="briefing-type" style="color:${b.type==='weekly'?'var(--purple)':'var(--blue)'}">
        ${b.type==='weekly'?'📅 주간 브리핑':'📄 일침 브리핑'}
      </div>
      <div class="briefing-content">${b.content}</div>
      <div class="briefing-date">${b.date}</div>
    </div>`).join('');
}

loadData();
loadPullupPR();
loadBriefings();
</script>

<!-- 운동 모달 -->
<div class="modal-overlay" id="modal-workout">
  <div class="modal">
    <h3>💪 운동 추가</h3>
    <div class="form-row"><label>날짜</label><input type="date" id="w-date"></div>
    <div class="form-row"><label>운동 기록 (한 번에 통으로 입력)</label>
      <textarea id="w-text" rows="3" placeholder="예: 스쿼트 100kg 5x10, 레그프레스 80kg 4x12, 풀업 15개"></textarea>
    </div>
    <button class="btn-submit" onclick="submitForm('workout',{date:document.getElementById('w-date').value||undefined,text:document.getElementById('w-text').value})">&#x2713; 저장</button>
    <button class="btn-cancel" onclick="closeModal('workout')">취소</button>
  </div>
</div>

<!-- 식단 모달 -->
<div class="modal-overlay" id="modal-diet">
  <div class="modal">
    <h3>🥗 식단 추가</h3>
    <div class="form-row"><label>날짜</label><input type="date" id="d-date"></div>
    <div class="form-row"><label>식사 시간</label>
      <select id="d-meal"><option value="">선택</option><option>아침</option><option>점심</option><option>저녁</option><option>간식</option></select></div>
    <div class="form-row"><label>메뉴</label><textarea id="d-items" rows="3" placeholder="닭가슴살 200g, 밥 1공기..."></textarea></div>
    <div class="form-row"><label>단백질 (g, 선택)</label><input type="number" id="d-protein" placeholder="-"></div>
    <button class="btn-submit" onclick="submitForm('diet',{date:document.getElementById('d-date').value||undefined,meal:document.getElementById('d-meal').value||undefined,items:document.getElementById('d-items').value,protein_g:document.getElementById('d-protein').value||null})">&#x2713; 저장</button>
    <button class="btn-cancel" onclick="closeModal('diet')">취소</button>
  </div>
</div>

<!-- 바이탈 모달 -->
<div class="modal-overlay" id="modal-vital">
  <div class="modal">
    <h3>⚖️ 바이탈 추가</h3>
    <div class="form-row"><label>날짜</label><input type="date" id="v-date"></div>
    <div class="form-grid2">
      <div class="form-row"><label>체중 (kg)</label><input type="number" id="v-weight" step="0.1" placeholder="-"></div>
      <div class="form-row"><label>수면 (시간)</label><input type="number" id="v-sleep" step="0.5" placeholder="-"></div>
    </div>
    <div class="form-row"><label>컨디션</label>
      <select id="v-cond"><option value="">선택</option><option value="excellent">최고</option><option value="good">좋음</option><option value="fair">보통</option><option value="tired">피곤</option><option value="poor">나쁨</option></select></div>
    <div class="form-row"><label>음주</label>
      <select id="v-alcohol"><option value="0">없음</option><option value="1">함</option></select></div>
    <button class="btn-submit" onclick="submitForm('vital',{date:document.getElementById('v-date').value||undefined,weight_kg:document.getElementById('v-weight').value||null,sleep_hours:document.getElementById('v-sleep').value||null,condition:document.getElementById('v-cond').value||null,alcohol:document.getElementById('v-alcohol').value})">&#x2713; 저장</button>
    <button class="btn-cancel" onclick="closeModal('vital')">취소</button>
  </div>
</div>

<!-- 운동 수정 모달 -->
<div class="modal-overlay" id="modal-edit-workout">
  <div class="modal">
    <h3>✏️ 운동 기록 수정</h3>
    <input type="hidden" id="ew-id">
    <div class="form-row"><label>날짜</label><input type="date" id="ew-date"></div>
    <div class="form-row"><label>운동 이름</label><input type="text" id="ew-exercise"></div>
    <div class="form-grid2">
      <div class="form-row"><label>세트</label><input type="number" id="ew-sets" min="1"></div>
      <div class="form-row"><label>횟수</label><input type="number" id="ew-reps" min="1"></div>
    </div>
    <div class="form-row"><label>무게 (kg)</label><input type="number" id="ew-weight" step="0.5" placeholder="-"></div>
    <button class="btn-submit" onclick="submitEditForm('workout')">&#x2713; 수정 저장</button>
    <button class="btn-cancel" onclick="closeEditModal('workout')">취소</button>
  </div>
</div>

<!-- 식단 수정 모달 -->
<div class="modal-overlay" id="modal-edit-diet">
  <div class="modal">
    <h3>✏️ 식단 기록 수정</h3>
    <input type="hidden" id="ed-id">
    <div class="form-row"><label>날짜</label><input type="date" id="ed-date"></div>
    <div class="form-row"><label>식사 시간</label>
      <select id="ed-meal"><option value="">선택</option><option>아침</option><option>점심</option><option>저녁</option><option>간식</option></select></div>
    <div class="form-row"><label>메뉴</label><textarea id="ed-items" rows="3"></textarea></div>
    <div class="form-row"><label>단백질 (g)</label><input type="number" id="ed-protein" placeholder="-"></div>
    <button class="btn-submit" onclick="submitEditForm('diet')">&#x2713; 수정 저장</button>
    <button class="btn-cancel" onclick="closeEditModal('diet')">취소</button>
  </div>
</div>

<!-- 바이탈 수정 모달 -->
<div class="modal-overlay" id="modal-edit-vital">
  <div class="modal">
    <h3>✏️ 바이탈 기록 수정</h3>
    <input type="hidden" id="ev-id">
    <div class="form-row"><label>날짜</label><input type="date" id="ev-date"></div>
    <div class="form-grid2">
      <div class="form-row"><label>체중 (kg)</label><input type="number" id="ev-weight" step="0.1" placeholder="-"></div>
      <div class="form-row"><label>수면 (시간)</label><input type="number" id="ev-sleep" step="0.5" placeholder="-"></div>
    </div>
    <div class="form-row"><label>컨디션</label>
      <select id="ev-cond"><option value="">선택</option><option value="excellent">최고</option><option value="good">좋음</option><option value="fair">보통</option><option value="tired">피곤</option><option value="poor">나쁨</option></select></div>
    <div class="form-row"><label>음주</label>
      <select id="ev-alcohol"><option value="0">없음</option><option value="1">함</option></select></div>
    <button class="btn-submit" onclick="submitEditForm('vital')">&#x2713; 수정 저장</button>
    <button class="btn-cancel" onclick="closeEditModal('vital')">취소</button>
  </div>
</div>

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
        "SELECT id, date, exercise, sets, reps, weight_kg FROM workouts ORDER BY date DESC, id DESC LIMIT 10")

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
        "SELECT id, date, exercise, sets, reps, weight_kg FROM workouts ORDER BY date DESC, id DESC LIMIT 200"))


@app.route("/api/diet")
def api_diet():
    return jsonify(db_query(
        "SELECT id, date, meal, items, protein_g FROM diet ORDER BY date DESC, id DESC LIMIT 100"))


@app.route("/api/vitals")
def api_vitals():
    return jsonify(db_query(
        "SELECT id, date, weight_kg, sleep_hours, condition, alcohol FROM vitals ORDER BY date DESC LIMIT 60"))


@app.route("/api/delete/workout/<int:rec_id>", methods=["POST", "DELETE"])
def delete_workout(rec_id):
    con = get_db()
    con.execute("DELETE FROM workouts WHERE id=?", (rec_id,))
    con.commit(); con.close()
    return jsonify({"ok": True})


@app.route("/api/delete/diet/<int:rec_id>", methods=["POST", "DELETE"])
def delete_diet(rec_id):
    con = get_db()
    con.execute("DELETE FROM diet WHERE id=?", (rec_id,))
    con.commit(); con.close()
    return jsonify({"ok": True})


@app.route("/api/delete/vital/<int:rec_id>", methods=["POST", "DELETE"])
def delete_vital(rec_id):
    con = get_db()
    con.execute("DELETE FROM vitals WHERE id=?", (rec_id,))
    con.commit(); con.close()
    return jsonify({"ok": True})


@app.route("/api/edit/workout/<int:rec_id>", methods=["POST"])
def edit_workout(rec_id):
    d = request.json
    con = get_db()
    con.execute(
        "UPDATE workouts SET date=?, exercise=?, sets=?, reps=?, weight_kg=? WHERE id=?",
        (d["date"], d["exercise"], int(d["sets"]) if d.get("sets") else None,
         int(d["reps"]) if d.get("reps") else None,
         float(d["weight_kg"]) if d.get("weight_kg") else None, rec_id)
    )
    con.commit(); con.close()
    return jsonify({"ok": True})


@app.route("/api/edit/diet/<int:rec_id>", methods=["POST"])
def edit_diet(rec_id):
    d = request.json
    con = get_db()
    con.execute(
        "UPDATE diet SET date=?, meal=?, items=?, protein_g=? WHERE id=?",
        (d["date"], d.get("meal"), d["items"],
         float(d["protein_g"]) if d.get("protein_g") else None, rec_id)
    )
    con.commit(); con.close()
    return jsonify({"ok": True})


@app.route("/api/edit/vital/<int:rec_id>", methods=["POST"])
def edit_vital(rec_id):
    d = request.json
    con = get_db()
    con.execute(
        "UPDATE vitals SET date=?, weight_kg=?, sleep_hours=?, condition=?, alcohol=? WHERE id=?",
        (d["date"], float(d["weight_kg"]) if d.get("weight_kg") else None,
         float(d["sleep_hours"]) if d.get("sleep_hours") else None,
         d.get("condition"), int(d.get("alcohol", 0)), rec_id)
    )
    con.commit(); con.close()
    return jsonify({"ok": True})


@app.route("/api/add/workout", methods=["POST"])
def add_workout():
    d = request.json
    today = d.get("date") or date.today().isoformat()
    now = datetime.now().isoformat()
    raw_text = d.get("text", "").strip() or d.get("exercise", "").strip()

    try:
        from save_message import parse_workouts
        parsed = parse_workouts(raw_text)
    except Exception:
        import re
        parsed = []
        pats = [
            r'([가-힣a-zA-Z\s\-]{2,15}?)\s+(?:(\d+(?:\.\d+)?)\s*kg\s+)?(\d+)\s*[xX×]\s*(\d+)',
            r'([가-힣a-zA-Z\s\-]{2,15}?)\s+(?:(\d+(?:\.\d+)?)\s*kg\s+)?(\d+)\s*세트\s*(\d+)\s*회',
        ]
        skip = {'수면', '체중', '단백질', '오늘', '어제', '아침', '점심', '저녁', '간식'}
        for pat in pats:
            for m in re.finditer(pat, raw_text):
                name = m.group(1).strip()
                if len(name) >= 2 and name not in skip:
                    parsed.append({'exercise': name, 'sets': int(m.group(3)), 'reps': int(m.group(4)), 'weight_kg': float(m.group(2)) if m.group(2) else None})

    con = get_db()
    if parsed:
        for w in parsed:
            con.execute(
                "INSERT INTO workouts (date,exercise,sets,reps,weight_kg,raw,created_at) VALUES(?,?,?,?,?,?,?)",
                (today, w['exercise'], w['sets'], w['reps'], w['weight_kg'], raw_text, now)
            )
    else:
        con.execute(
            "INSERT INTO workouts (date,exercise,sets,reps,weight_kg,raw,created_at) VALUES(?,?,?,?,?,?,?)",
            (today, raw_text, int(d.get("sets")) if d.get("sets") else None,
             int(d.get("reps")) if d.get("reps") else None,
             float(d.get("weight_kg")) if d.get("weight_kg") else None, raw_text, now)
        )
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.route("/api/add/diet", methods=["POST"])
def add_diet():
    d = request.json
    today = d.get("date", date.today().isoformat())
    now = datetime.now().isoformat()
    con = get_db()
    con.execute(
        "INSERT INTO diet (date,meal,items,protein_g,raw,created_at) VALUES(?,?,?,?,?,?)",
        (today, d.get("meal"), d["items"],
         float(d["protein_g"]) if d.get("protein_g") else None, "web", now))
    con.commit(); con.close()
    return jsonify({"ok": True})


@app.route("/api/add/vital", methods=["POST"])
def add_vital():
    d = request.json
    today = d.get("date", date.today().isoformat())
    now = datetime.now().isoformat()
    con = get_db()
    try:
        con.execute(
            "INSERT INTO vitals (date,weight_kg,sleep_hours,condition,alcohol,raw,created_at) VALUES(?,?,?,?,?,?,?)",
            (today, float(d["weight_kg"]) if d.get("weight_kg") else None,
             float(d["sleep_hours"]) if d.get("sleep_hours") else None,
             d.get("condition"), int(d.get("alcohol", 0)), "web", now))
    except sqlite3.IntegrityError:
        con.execute(
            "UPDATE vitals SET weight_kg=?,sleep_hours=?,condition=?,alcohol=? WHERE date=?",
            (float(d["weight_kg"]) if d.get("weight_kg") else None,
             float(d["sleep_hours"]) if d.get("sleep_hours") else None,
             d.get("condition"), int(d.get("alcohol", 0)), today))
    con.commit(); con.close()
    return jsonify({"ok": True})


@app.route("/api/briefings")
def get_briefings():
    return jsonify(db_query(
        "SELECT date, type, content FROM briefings ORDER BY date DESC, id DESC LIMIT 10"))


@app.route("/api/add/briefing", methods=["POST"])
def add_briefing():
    d = request.json
    con = get_db()
    con.execute(
        "INSERT INTO briefings (date,type,content,created_at) VALUES(?,?,?,?)",
        (d.get("date", date.today().isoformat()), d.get("type", "daily"),
         d["content"], datetime.now().isoformat()))
    con.commit(); con.close()
    return jsonify({"ok": True})


@app.route("/api/pullup-pr")
def pullup_pr():
    row = db_one(
        "SELECT MAX(reps) as pr, date FROM workouts WHERE exercise LIKE '%풀업%' ORDER BY pr DESC")
    daily = db_query(
        "SELECT date, MAX(reps) as max_reps FROM workouts WHERE exercise LIKE '%풀업%' GROUP BY date ORDER BY date DESC LIMIT 30")
    return jsonify({"pr": row.get("pr"), "pr_date": row.get("date"), "daily": daily})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
