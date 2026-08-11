from pathlib import Path
import sys
import json
from datetime import date, timedelta

# 프로젝트 경로 설정
sys.path.append(str(Path("/home/ubuntu/pt_system")))
sys.path.append(str(Path(__file__).resolve().parents[1]))

from flask import Flask, render_template_string, request, redirect, url_for
from scripts.db import get_conn

app = Flask(__name__)

# 대시보드 HTML 템플릿
HTML = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI PT 대시보드</title>
  <!-- Google Fonts & Lucide Icons -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;600;700;800&display=swap" rel="stylesheet">
  <script src="https://unpkg.com/lucide@latest"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg-primary: #0b0f19;
      --bg-secondary: #131a26;
      --bg-tertiary: #1b2434;
      --accent-cyan: #06b6d4;
      --accent-emerald: #10b981;
      --accent-purple: #8b5cf6;
      --accent-amber: #f59e0b;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --border-color: #243048;
      --card-shadow: 0 4px 20px 0 rgba(0, 0, 0, 0.3);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    
    body {
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background-color: var(--bg-primary);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    header {
      background: linear-gradient(135deg, var(--bg-secondary) 0%, #0f172a 100%);
      border-bottom: 1px solid var(--border-color);
      padding: 24px 40px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }

    .brand-section {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-icon {
      background: linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-purple) 100%);
      width: 42px;
      height: 42px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      box-shadow: 0 0 15px rgba(6, 182, 212, 0.4);
    }

    header h1 {
      font-family: 'Outfit', sans-serif;
      font-size: 26px;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(to right, #ffffff, #93c5fd);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    header p {
      font-size: 14px;
      color: var(--text-muted);
      margin-top: 2px;
    }

    .nav-tabs {
      display: flex;
      gap: 8px;
      background-color: var(--bg-primary);
      padding: 6px;
      border-radius: 10px;
      border: 1px solid var(--border-color);
    }

    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 10px 18px;
      font-size: 14px;
      font-weight: 600;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s ease;
    }

    .tab-btn:hover {
      color: var(--text-main);
      background-color: rgba(255, 255, 255, 0.05);
    }

    .tab-btn.active {
      color: white;
      background-color: var(--bg-tertiary);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
      border: 1px solid var(--border-color);
    }

    main {
      flex: 1;
      max-width: 1280px;
      width: 100%;
      margin: 0 auto;
      padding: 32px 40px;
    }

    .grid-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 20px;
      margin-bottom: 32px;
    }

    .stat-card {
      background-color: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: relative;
      overflow: hidden;
      box-shadow: var(--card-shadow);
      transition: transform 0.2s ease, border-color 0.2s ease;
    }

    .stat-card:hover {
      transform: translateY(-4px);
      border-color: rgba(255, 255, 255, 0.15);
    }

    .stat-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 4px;
      height: 100%;
    }

    .stat-card.workouts::before { background-color: var(--accent-cyan); }
    .stat-card.meals::before { background-color: var(--accent-emerald); }
    .stat-card.vitals::before { background-color: var(--accent-purple); }
    .stat-card.weight::before { background-color: var(--accent-amber); }

    .stat-label {
      font-size: 13px;
      text-transform: uppercase;
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 0.5px;
    }

    .stat-value {
      font-family: 'Outfit', sans-serif;
      font-size: 32px;
      font-weight: 800;
      color: white;
      margin-top: 6px;
    }

    .stat-icon {
      background-color: var(--bg-tertiary);
      width: 50px;
      height: 50px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 1px solid var(--border-color);
    }

    .stat-card.workouts .stat-icon { color: var(--accent-cyan); }
    .stat-card.meals .stat-icon { color: var(--accent-emerald); }
    .stat-card.vitals .stat-icon { color: var(--accent-purple); }
    .stat-card.weight .stat-icon { color: var(--accent-amber); }

    .dashboard-content {
      display: none;
      animation: fadeIn 0.3s ease-in-out forwards;
    }

    .dashboard-content.active {
      display: block;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .dashboard-grid {
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 24px;
    }

    .card {
      background-color: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 28px;
      box-shadow: var(--card-shadow);
      margin-bottom: 24px;
    }

    .card-title {
      font-family: 'Outfit', sans-serif;
      font-size: 20px;
      font-weight: 700;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      gap: 10px;
      color: white;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 12px;
    }

    .card-title i {
      color: var(--accent-cyan);
    }

    .report-box {
      background-color: var(--bg-tertiary);
      border-radius: 12px;
      padding: 24px;
      border: 1px solid var(--border-color);
      font-size: 15px;
      line-height: 1.7;
      white-space: pre-wrap;
      color: #e2e8f0;
      position: relative;
    }

    .report-box::after {
      content: '""';
      position: absolute;
      right: 20px;
      bottom: 10px;
      font-size: 80px;
      color: rgba(255, 255, 255, 0.03);
      font-family: serif;
      line-height: 1;
    }

    .table-container {
      overflow-x: auto;
      border-radius: 12px;
      border: 1px solid var(--border-color);
      background-color: var(--bg-secondary);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }

    th {
      background-color: var(--bg-tertiary);
      color: var(--text-muted);
      font-weight: 600;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border-color);
    }

    td {
      padding: 16px 18px;
      border-bottom: 1px solid var(--border-color);
      color: #cbd5e1;
      font-size: 14px;
      vertical-align: middle;
    }

    tr:last-child td {
      border-bottom: none;
    }

    tr:hover td {
      background-color: rgba(255, 255, 255, 0.02);
    }

    .badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }

    .badge-breakfast { background-color: rgba(16, 185, 129, 0.15); color: #34d399; }
    .badge-lunch { background-color: rgba(245, 158, 11, 0.15); color: #fbbf24; }
    .badge-dinner { background-color: rgba(6, 182, 212, 0.15); color: #22d3ee; }
    .badge-snack { background-color: rgba(139, 92, 246, 0.15); color: #a78bfa; }
    .badge-default { background-color: rgba(156, 163, 175, 0.15); color: #d1d5db; }

    .condition-text {
      background-color: var(--bg-tertiary);
      border-radius: 6px;
      padding: 4px 8px;
      font-size: 12px;
      border: 1px solid var(--border-color);
      color: var(--text-main);
    }

    .date-col {
      font-weight: 500;
      color: var(--text-muted);
      white-space: nowrap;
    }

    .exercise-badge {
      background-color: rgba(6, 182, 212, 0.1);
      color: var(--accent-cyan);
      border: 1px solid rgba(6, 182, 212, 0.2);
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 13px;
    }

    .empty-state {
      text-align: center;
      padding: 40px 20px;
      color: var(--text-muted);
      font-size: 14px;
    }

    .empty-state i {
      display: block;
      margin: 0 auto 12px;
      color: var(--border-color);
    }

    @media (max-width: 1024px) {
      .dashboard-grid { grid-template-columns: 1fr; }
      .grid-stats { grid-template-columns: repeat(2, 1fr); }
    }

    @media (max-width: 768px) {
      header { padding: 20px; flex-direction: column; align-items: stretch; }
      .nav-tabs { width: 100%; justify-content: space-around; }
      main { padding: 20px; }
      .grid-stats { grid-template-columns: 1fr; }
    }

    .delete-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      padding: 6px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
    }
    .delete-btn:hover {
      color: #ef4444;
      background-color: rgba(239, 68, 68, 0.1);
    }
    .delete-btn i {
      width: 16px;
      height: 16px;
    }

    /* Modal & Edit Button Styling */
    .modal {
      display: none;
      position: fixed;
      z-index: 1000;
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      overflow: auto;
      background-color: rgba(11, 15, 25, 0.8);
      backdrop-filter: blur(4px);
      align-items: center;
      justify-content: center;
    }
    .modal.active {
      display: flex;
    }
    .modal-content {
      background-color: var(--bg-secondary);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      width: 100%;
      max-width: 500px;
      padding: 28px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
      position: relative;
      animation: modalFadeIn 0.2s ease;
    }
    @keyframes modalFadeIn {
      from { transform: scale(0.95); opacity: 0; }
      to { transform: scale(1); opacity: 1; }
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 12px;
      color: white;
    }
    .modal-header h3 {
      font-family: 'Outfit', sans-serif;
      font-size: 18px;
      font-weight: 700;
    }
    .close-modal-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 20px;
      transition: color 0.2s;
    }
    .close-modal-btn:hover {
      color: white;
    }
    .form-group {
      margin-bottom: 16px;
    }
    .form-group label {
      display: block;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    .form-control {
      width: 100%;
      background-color: var(--bg-tertiary);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 10px 14px;
      color: white;
      font-size: 14px;
      font-family: inherit;
      transition: border-color 0.2s;
    }
    .form-control:focus {
      outline: none;
      border-color: var(--accent-cyan);
    }
    .modal-footer {
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      margin-top: 24px;
      border-top: 1px solid var(--border-color);
      padding-top: 16px;
    }
    .btn {
      padding: 10px 20px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      border: none;
    }
    .btn-secondary {
      background-color: var(--bg-tertiary);
      color: var(--text-main);
      border: 1px solid var(--border-color);
    }
    .btn-secondary:hover {
      background-color: rgba(255, 255, 255, 0.05);
    }
    .btn-primary {
      background: linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-purple) 100%);
      color: white;
    }
    .btn-primary:hover {
      box-shadow: 0 0 15px rgba(6, 182, 212, 0.4);
    }
    .edit-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      padding: 6px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
      margin-right: 4px;
    }
    .edit-btn:hover {
      color: var(--accent-cyan);
      background-color: rgba(6, 182, 212, 0.1);
    }
    .edit-btn i {
      width: 16px;
      height: 16px;
    }

    /* Calendar & Streak Banner Styling */
    .calendar-grid {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 6px;
      text-align: center;
      margin-top: 12px;
    }
    .calendar-day-header {
      font-size: 11px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      padding: 6px 0;
    }
    .calendar-day {
      background-color: var(--bg-tertiary);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      aspect-ratio: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-muted);
      position: relative;
      transition: all 0.2s ease;
    }
    .calendar-day.today {
      border-color: var(--accent-cyan);
      color: white;
    }
    .calendar-day.has-workout {
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(6, 182, 212, 0.15) 100%);
      border-color: var(--accent-emerald);
      color: #34d399;
      box-shadow: 0 0 10px rgba(16, 185, 129, 0.2);
    }
    .calendar-day.has-workout::after {
      content: '🔥';
      font-size: 9px;
      position: absolute;
      bottom: 2px;
    }
    .calendar-day.empty {
      background: transparent;
      border: none;
    }
    .calendar-header-title {
      font-family: 'Outfit', sans-serif;
      font-size: 16px;
      font-weight: 700;
      color: white;
      text-align: center;
      margin-bottom: 12px;
    }

    /* Challenge Grid Styling */
    .challenge-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 20px;
      margin-bottom: 24px;
    }
    @media (max-width: 992px) {
      .challenge-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <a href="/add" style="position:fixed;right:18px;bottom:18px;z-index:999;background:#06b6d4;color:#00121a;font-weight:700;text-decoration:none;padding:12px 18px;border-radius:999px;box-shadow:0 6px 20px rgba(0,0,0,.4);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">➕ 기록 추가</a>
  <header>
    <div class="brand-section">
      <div class="brand-icon">
        <i data-lucide="dumbbell"></i>
      </div>
      <div>
        <h1>AI PT 대시보드</h1>
        <p>운동, 식단, 체중, 리포트를 한 곳에서 실시간 확인합니다.</p>
      </div>
    </div>
    
    <div class="nav-tabs">
      <button class="tab-btn active" onclick="switchTab('tab-overview')">
        <i data-lucide="layout-dashboard"></i> 오버뷰
      </button>
      <button class="tab-btn" onclick="switchTab('tab-workouts')">
        <i data-lucide="activity"></i> 운동 기록
      </button>
      <button class="tab-btn" onclick="switchTab('tab-meals')">
        <i data-lucide="salad"></i> 식단 기록
      </button>
      <button class="tab-btn" onclick="switchTab('tab-vitals')">
        <i data-lucide="heart-pulse"></i> 체중 & 바이탈
      </button>
    </div>
  </header>

  <main>
    <!-- KPI Stats Section -->
    <section class="grid-stats">
      <div class="stat-card workouts">
        <div>
          <div class="stat-label">누적 운동 기록</div>
          <div class="stat-value">{{ workout_count }}</div>
        </div>
        <div class="stat-icon"><i data-lucide="flame"></i></div>
      </div>
      <div class="stat-card meals">
        <div>
          <div class="stat-label">누적 식단 기록</div>
          <div class="stat-value">{{ meal_count }}</div>
        </div>
        <div class="stat-icon"><i data-lucide="apple"></i></div>
      </div>
      <div class="stat-card vitals">
        <div>
          <div class="stat-label">누적 바이탈</div>
          <div class="stat-value">{{ vital_count }}</div>
        </div>
        <div class="stat-icon"><i data-lucide="scale"></i></div>
      </div>
      <div class="stat-card weight">
        <div>
          <div class="stat-label">최근 체중</div>
          <div class="stat-value">{{ latest_weight or "-" }} <span style="font-size:16px; font-weight:normal; color:var(--text-muted);">{{ "kg" if latest_weight else "" }}</span></div>
        </div>
        <div class="stat-icon"><i data-lucide="trending-up"></i></div>
      </div>
    </section>

    <!-- Tab 1: Overview -->
    <div id="tab-overview" class="dashboard-content active">
      <!-- Challenge Banners Grid -->
      <div class="challenge-grid">
        <!-- Streak Challenge Banner -->
        <div class="card streak-card" style="background: linear-gradient(135deg, #1e1b4b 0%, #311042 100%); border: 1px solid #4c1d95; margin-bottom: 0;">
          <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px;">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div style="background: rgba(245, 158, 11, 0.15); width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #f59e0b; box-shadow: 0 0 15px rgba(245, 158, 11, 0.3);">
                <i data-lucide="flame" style="width: 32px; height: 32px;"></i>
              </div>
              <div>
                <h3 style="font-family: 'Outfit', sans-serif; font-size: 20px; font-weight: 700; color: white;">연속 운동 챌린지</h3>
                <p style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">
                  {% if streak_count > 0 %}
                    오늘도 불꽃을 이어가세요! 현재 <strong>{{ streak_count }}일 연속</strong> 운동 달성 중입니다. 🔥
                  {% else %}
                    아직 연속 운동 기록이 없습니다. 오늘 가볍게 운동을 시작해서 첫 불꽃을 피워보세요!
                  {% endif %}
                </p>
              </div>
            </div>
            <div style="font-family: 'Outfit', sans-serif; font-size: 24px; font-weight: 800; color: #f59e0b; background: rgba(255, 255, 255, 0.05); padding: 8px 20px; border-radius: 12px; border: 1px solid rgba(245, 158, 11, 0.2); white-space: nowrap;">
              {{ streak_count }}일 연속
            </div>
          </div>
        </div>

        <!-- Pull-up Challenge Banner -->
        <div class="card pullup-card" style="background: linear-gradient(135deg, #064e3b 0%, #022c22 100%); border: 1px solid #065f46; margin-bottom: 0; display: flex; flex-direction: column; justify-content: space-between;">
          <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px;">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div style="background: rgba(16, 185, 129, 0.15); width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #34d399; box-shadow: 0 0 15px rgba(16, 185, 129, 0.3);">
                <i data-lucide="award" style="width: 32px; height: 32px;"></i>
              </div>
              <div>
                <h3 style="font-family: 'Outfit', sans-serif; font-size: 20px; font-weight: 700; color: white;">풀업 챌린지 (PR)</h3>
                <p style="font-size: 14px; color: var(--text-muted); margin-top: 4px;">
                  {% if pullup_pr > 0 %}
                    하루 최대 <strong>{{ pullup_pr }}회</strong> 성공! 최고 기록을 깨봅시다! 💪
                  {% else %}
                    아직 풀업 기록이 없습니다. 오늘 턱걸이 기록을 남겨보세요!
                  {% endif %}
                </p>
              </div>
            </div>
            <div style="font-family: 'Outfit', sans-serif; font-size: 24px; font-weight: 800; color: #34d399; background: rgba(255, 255, 255, 0.05); padding: 8px 20px; border-radius: 12px; border: 1px solid rgba(16, 185, 129, 0.2); white-space: nowrap;">
              최고 {{ pullup_pr }}회
            </div>
          </div>
          {% if pullup_history %}
          <div style="margin-top: 14px; border-top: 1px solid rgba(255, 255, 255, 0.08); padding-top: 10px; display: flex; gap: 10px; font-size: 11px; color: var(--text-muted); flex-wrap: wrap;">
            <span style="font-weight:600; color: white;">최근 기록:</span>
            {% for h in pullup_history %}
              <span style="background: rgba(255, 255, 255, 0.03); padding: 1px 6px; border-radius: 4px; border: 1px solid rgba(255, 255, 255, 0.05);">
                {{ h.date[5:] }} ({{ h.reps }}회)
              </span>
            {% endfor %}
          </div>
          {% endif %}
        </div>
      </div>

      <div class="dashboard-grid" style="margin-top: 24px;">
        <!-- Left column: AI Report -->
        <div class="card" style="margin-bottom: 0;">
          <div class="card-title">
            <i data-lucide="sparkles" style="color: var(--accent-purple);"></i> 최근 AI 피드백 리포트
          </div>
          {% if latest_report %}
          <div class="report-box">{{ latest_report }}</div>
          {% else %}
          <div class="empty-state">
            <i data-lucide="message-square-off" size="48"></i>
            아직 리포트가 생성되지 않았습니다. 텔레그램에서 /daily 또는 /weekly를 입력해 리포트를 생성해 보세요.
          </div>
          {% endif %}
        </div>

        <!-- Right column: Calendar & Quick overview -->
        <div>
          <!-- Calendar Card -->
          <div class="card">
            <div class="card-title">
              <i data-lucide="calendar" style="color: var(--accent-emerald);"></i> 이번 달 운동 달력
            </div>
            <div id="calendar-container"></div>
          </div>

          <!-- Existing Workout List Card -->
          <div class="card" style="margin-bottom: 0; margin-top: 24px;">
            <div class="card-title">
              <i data-lucide="clock" style="color: var(--accent-amber);"></i> 실시간 운동 현황
            </div>
            {% if workouts %}
            <div class="table-container">
              <table>
                <thead>
                  <tr>
                    <th>운동</th>
                    <th>날짜</th>
                  </tr>
                </thead>
                <tbody>
                  {% for row in workouts[:5] %}
                  <tr>
                    <td><span class="exercise-badge">{{ row.exercise_name }}</span></td>
                    <td class="date-col">{{ row.record_date }}</td>
                  </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
            {% else %}
            <div class="empty-state">
              <i data-lucide="clipboard-list" size="48"></i>
              오늘 등록된 운동 내역이 없습니다.
            </div>
            {% endif %}
          </div>
        </div>
      </div>
    </div>

    <!-- Tab 2: Workouts -->
    <div id="tab-workouts" class="dashboard-content">
      <div class="card">
        <div class="card-title"><i data-lucide="activity"></i> 전체 운동 기록 내역</div>
        {% if workouts %}
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th style="width: 150px;">날짜</th>
                <th style="width: 250px;">운동 종목</th>
                <th>상세 메모</th>
                <th style="width: 100px; text-align: center;">관리</th>
              </tr>
            </thead>
            <tbody>
              {% for row in workouts %}
              <tr>
                <td class="date-col">{{ row.record_date }}</td>
                <td><span class="exercise-badge">{{ row.exercise_name }}</span></td>
                <td>{{ row.memo or "-" }}</td>
                <td style="text-align: center;">
                  <button class="edit-btn" 
                          data-category="workouts" 
                          data-id="{{ row.id }}" 
                          data-date="{{ row.record_date }}" 
                          data-name="{{ row.exercise_name }}" 
                          data-content="{{ row.memo or '' }}"
                          onclick="triggerEdit(this)" 
                          title="수정">
                    <i data-lucide="edit-3"></i>
                  </button>
                  <button class="delete-btn" onclick="deleteRecord('workouts', {{ row.id }})" title="삭제">
                    <i data-lucide="trash-2"></i>
                  </button>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <div class="empty-state">
          <i data-lucide="award" size="48"></i>
          운동 기록이 비어 있습니다. 텔레그램을 통해 첫 운동을 등록해 보세요!
        </div>
        {% endif %}
      </div>
    </div>

    <!-- Tab 3: Meals -->
    <div id="tab-meals" class="dashboard-content">
      <div class="card">
        <div class="card-title"><i data-lucide="salad"></i> 전체 식단 기록 내역</div>
        {% if meals %}
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th style="width: 150px;">날짜</th>
                <th style="width: 120px;">식사 구분</th>
                <th>메뉴 및 상세 내용</th>
                <th style="width: 100px; text-align: center;">관리</th>
              </tr>
            </thead>
            <tbody>
              {% for row in meals %}
              <tr>
                <td class="date-col">{{ row.record_date }}</td>
                <td>
                  {% if row.meal_type == '아침' %}
                    <span class="badge badge-breakfast">아침</span>
                  {% elif row.meal_type == '점심' %}
                    <span class="badge badge-lunch">점심</span>
                  {% elif row.meal_type == '저녁' %}
                    <span class="badge badge-dinner">저녁</span>
                  {% elif row.meal_type == '간식' %}
                    <span class="badge badge-snack">간식</span>
                  {% else %}
                    <span class="badge badge-default">{{ row.meal_type or "미분류" }}</span>
                  {% endif %}
                </td>
                <td>{{ row.food_text }}</td>
                <td style="text-align: center;">
                  <button class="edit-btn" 
                          data-category="meals" 
                          data-id="{{ row.id }}" 
                          data-date="{{ row.record_date }}" 
                          data-name="{{ row.meal_type or '미분류' }}" 
                          data-content="{{ row.food_text or '' }}"
                          onclick="triggerEdit(this)" 
                          title="수정">
                    <i data-lucide="edit-3"></i>
                  </button>
                  <button class="delete-btn" onclick="deleteRecord('meals', {{ row.id }})" title="삭제">
                    <i data-lucide="trash-2"></i>
                  </button>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <div class="empty-state">
          <i data-lucide="cookie" size="48"></i>
          식단 기록이 비어 있습니다. 오늘 먹은 음식을 텔레그램에 적어 보세요!
        </div>
        {% endif %}
      </div>
    </div>

    <!-- Tab 4: Vitals -->
    <div id="tab-vitals" class="dashboard-content">
      <!-- Weight Trend Chart -->
      <div class="card">
        <div class="card-title">
          <i data-lucide="trending-down" style="color: var(--accent-cyan);"></i> 체중 변화 추이 (최근 기록)
        </div>
        <div style="position: relative; height: 300px; width: 100%;">
          <canvas id="weightChart"></canvas>
        </div>
      </div>

      <div class="card" style="margin-top: 24px;">
        <div class="card-title"><i data-lucide="scale"></i> 체중 & 수면 및 컨디션 기록</div>
        {% if vitals %}
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th style="width: 180px;">날짜</th>
                <th style="width: 150px;">체중 (kg)</th>
                <th style="width: 150px;">수면 시간 (시간)</th>
                <th>컨디션 및 메모</th>
                <th style="width: 80px; text-align: center;">삭제</th>
              </tr>
            </thead>
            <tbody>
              {% for row in vitals %}
              <tr>
                <td class="date-col">{{ row.record_date }}</td>
                <td style="font-weight: 600; color: white;">{{ row.body_weight_kg or "-" }} {{ "kg" if row.body_weight_kg else "" }}</td>
                <td>{{ row.sleep_hours or "-" }} {{ "시간" if row.sleep_hours else "" }}</td>
                <td>
                  {% if row.condition_text %}
                    <span class="condition-text">{{ row.condition_text }}</span>
                  {% else %}
                    -
                  {% endif %}
                </td>
                <td style="text-align: center;">
                  <button class="delete-btn" onclick="deleteRecord('vitals', {{ row.id }})" title="삭제">
                    <i data-lucide="trash-2"></i>
                  </button>
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <div class="empty-state">
          <i data-lucide="line-chart" size="48"></i>
          바이탈 기록이 아직 없습니다. 체중이나 수면 시간을 입력해 보세요!
        </div>
        {% endif %}
      </div>
    </div>
  </main>

  <script>
    // Lucide 아이콘 초기화
    lucide.createIcons();

    // 탭 전환 함수
    function switchTab(tabId) {
      // 모든 탭 콘텐츠 숨기기
      const contents = document.querySelectorAll('.dashboard-content');
      contents.forEach(c => c.classList.remove('active'));

      // 모든 탭 버튼 active 클래스 해제
      const buttons = document.querySelectorAll('.tab-btn');
      buttons.forEach(b => b.classList.remove('active'));

      // 선택한 탭 콘텐츠 표시 및 버튼 활성화
      const targetContent = document.getElementById(tabId);
      if (targetContent) {
        targetContent.classList.add('active');
      }
      
      // 해당 탭을 트리거하는 버튼 활성화
      const targetBtn = Array.from(buttons).find(b => b.getAttribute('onclick').includes(tabId));
      if (targetBtn) {
        targetBtn.classList.add('active');
      }

      // sessionStorage에 현재 탭 상태 저장
      sessionStorage.setItem('activeTab', tabId);
    }

    // 페이지 로드 시 기존 탭 상태 복원 및 신규 구성요소 초기화
    window.addEventListener('DOMContentLoaded', () => {
      const savedTab = sessionStorage.getItem('activeTab');
      if (savedTab && document.getElementById(savedTab)) {
        switchTab(savedTab);
      } else {
        switchTab('tab-overview');
      }

      // 달력 및 차트 렌더링
      const workoutDates = {{ workout_dates_json | safe }};
      renderCalendar(workoutDates);

      const weightLabels = {{ weight_labels_json | safe }};
      const weightValues = {{ weight_values_json | safe }};
      renderWeightChart(weightLabels, weightValues);
    });

    // 달력 렌더링 함수
    function renderCalendar(workoutDates) {
      const container = document.getElementById('calendar-container');
      if (!container) return;

      const today = new Date();
      const year = today.getFullYear();
      const month = today.getMonth(); // 0-11

      const monthNames = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];
      
      let html = `<div class="calendar-header-title">${year}년 ${monthNames[month]}</div>`;
      html += `<div class="calendar-grid">`;
      
      const daysOfWeek = ["일", "월", "화", "수", "목", "금", "토"];
      daysOfWeek.forEach(d => {
        html += `<div class="calendar-day-header">${d}</div>`;
      });

      const firstDayIndex = new Date(year, month, 1).getDay();
      const totalDays = new Date(year, month + 1, 0).getDate();

      for (let i = 0; i < firstDayIndex; i++) {
        html += `<div class="calendar-day empty"></div>`;
      }

      for (let day = 1; day <= totalDays; day++) {
        const dStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const hasWorkout = workoutDates.includes(dStr);
        const isToday = day === today.getDate();

        let dayClass = "calendar-day";
        if (hasWorkout) dayClass += " has-workout";
        if (isToday) dayClass += " today";

        html += `<div class="${dayClass}">${day}</div>`;
      }

      html += `</div>`;
      container.innerHTML = html;
    }

    // 체중 차트 렌더링 함수
    function renderWeightChart(labels, values) {
      const ctx = document.getElementById('weightChart');
      if (!ctx) return;

      new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: '체중 (kg)',
            data: values,
            borderColor: '#06b6d4',
            backgroundColor: 'rgba(6, 182, 212, 0.1)',
            borderWidth: 3,
            fill: true,
            tension: 0.3,
            pointBackgroundColor: '#06b6d4',
            pointBorderColor: '#ffffff',
            pointHoverBackgroundColor: '#ffffff',
            pointHoverBorderColor: '#06b6d4',
            pointRadius: 4,
            pointHoverRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: false
            },
            tooltip: {
              backgroundColor: '#131a26',
              titleColor: '#9ca3af',
              bodyColor: '#ffffff',
              borderColor: '#243048',
              borderWidth: 1,
              padding: 10,
              displayColors: false
            }
          },
          scales: {
            x: {
              grid: {
                color: 'rgba(36, 48, 72, 0.5)'
              },
              ticks: {
                color: '#9ca3af',
                font: {
                  size: 11
                }
              }
            },
            y: {
              grid: {
                color: 'rgba(36, 48, 72, 0.5)'
              },
              ticks: {
                color: '#9ca3af',
                font: {
                  size: 11
                }
              }
            }
          }
        }
      });
    }

    // 기록 삭제 함수
    function deleteRecord(category, id) {
      if (confirm('정말로 이 기록을 삭제하시겠습니까?')) {
        fetch('/delete/' + category + '/' + id, {
          method: 'POST'
        }).then(response => {
          if (response.ok) {
            location.reload();
          } else {
            alert('삭제에 실패했습니다.');
          }
        }).catch(err => {
          console.error(err);
          alert('오류가 발생했습니다.');
        });
      }
    }

    // 모달 데이터 로드 대행 함수
    function triggerEdit(btn) {
      const category = btn.getAttribute('data-category');
      const id = btn.getAttribute('data-id');
      const dateVal = btn.getAttribute('data-date');
      const nameVal = btn.getAttribute('data-name');
      const contentVal = btn.getAttribute('data-content');
      openEditModal(category, id, dateVal, nameVal, contentVal);
    }

    // 모달 열기 함수
    function openEditModal(category, id, dateVal, typeOrNameVal, contentVal) {
      document.getElementById('editCategory').value = category;
      document.getElementById('editId').value = id;
      document.getElementById('editDate').value = dateVal;
      
      const modalTitle = document.getElementById('modalTitle');
      const groupExerciseName = document.getElementById('groupExerciseName');
      const groupMealType = document.getElementById('groupMealType');
      const labelContent = document.getElementById('labelContent');
      
      if (category === 'workouts') {
        modalTitle.innerText = "운동 기록 수정";
        groupExerciseName.style.display = "block";
        groupMealType.style.display = "none";
        document.getElementById('editExerciseName').value = typeOrNameVal;
        labelContent.innerText = "상세 메모";
        document.getElementById('editContent').value = contentVal;
      } else if (category === 'meals') {
        modalTitle.innerText = "식단 기록 수정";
        groupExerciseName.style.display = "none";
        groupMealType.style.display = "block";
        document.getElementById('editMealType').value = typeOrNameVal;
        labelContent.innerText = "메뉴 및 상세 내용";
        document.getElementById('editContent').value = contentVal;
      }
      
      document.getElementById('editModal').classList.add('active');
    }

    // 모달 닫기 함수
    function closeEditModal() {
      document.getElementById('editModal').classList.remove('active');
    }

    // 수정 내용 저장 제출
    function saveEdit(e) {
      e.preventDefault();
      
      const category = document.getElementById('editCategory').value;
      const id = document.getElementById('editId').value;
      
      const formData = new FormData();
      formData.append('record_date', document.getElementById('editDate').value);
      
      if (category === 'workouts') {
        formData.append('exercise_name', document.getElementById('editExerciseName').value);
        formData.append('memo', document.getElementById('editContent').value);
      } else if (category === 'meals') {
        formData.append('meal_type', document.getElementById('editMealType').value);
        formData.append('food_text', document.getElementById('editContent').value);
      }
      
      fetch('/edit/' + category + '/' + id, {
        method: 'POST',
        body: formData
      }).then(response => {
        if (response.ok) {
          location.reload();
        } else {
          alert('수정에 실패했습니다.');
        }
      }).catch(err => {
        console.error(err);
        alert('오류가 발생했습니다.');
      });
    }
  </script>

  <!-- Edit Modal Layout -->
  <div id="editModal" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <h3 id="modalTitle">기록 수정</h3>
        <button class="close-modal-btn" onclick="closeEditModal()">&times;</button>
      </div>
      <form id="editForm" onsubmit="saveEdit(event)">
        <input type="hidden" id="editCategory">
        <input type="hidden" id="editId">
        
        <div class="form-group">
          <label for="editDate">날짜</label>
          <input type="date" id="editDate" class="form-control" required>
        </div>
        
        <!-- For Workouts: Exercise Name -->
        <div class="form-group" id="groupExerciseName" style="display: none;">
          <label for="editExerciseName">운동 종목</label>
          <input type="text" id="editExerciseName" class="form-control">
        </div>
        
        <!-- For Meals: Meal Type -->
        <div class="form-group" id="groupMealType" style="display: none;">
          <label for="editMealType">식사 구분</label>
          <select id="editMealType" class="form-control">
            <option value="아침">아침</option>
            <option value="점심">점심</option>
            <option value="저녁">저녁</option>
            <option value="간식">간식</option>
          </select>
        </div>
        
        <!-- Text content (Memo/Food Text) -->
        <div class="form-group">
          <label for="editContent" id="labelContent">상세 내용</label>
          <textarea id="editContent" class="form-control" rows="4" required></textarea>
        </div>
        
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" onclick="closeEditModal()">취소</button>
          <button type="submit" class="btn btn-primary">저장</button>
        </div>
      </form>
    </div>
  </div>
</body>
</html>
"""

from datetime import date, timedelta
import json

def calculate_streak(workout_dates):
    parsed_dates = set()
    for d_str in workout_dates:
        try:
            parsed_dates.add(date.fromisoformat(d_str))
        except ValueError:
            continue
            
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    if today in parsed_dates:
        start_date = today
    elif yesterday in parsed_dates:
        start_date = yesterday
    else:
        return 0
        
    streak = 0
    current_check = start_date
    while current_check in parsed_dates:
        streak += 1
        current_check -= timedelta(days=1)
        
    return streak


@app.route("/edit/<string:category>/<int:record_id>", methods=["POST"])
def edit_record(category, record_id):
    if category not in ["workouts", "meals"]:
        return "Invalid category", 400
        
    conn = get_conn()
    try:
        if category == "workouts":
            record_date = request.form.get("record_date")
            exercise_name = request.form.get("exercise_name")
            memo = request.form.get("memo")
            conn.execute(
                "UPDATE workouts SET record_date = ?, exercise_name = ?, memo = ? WHERE id = ?",
                (record_date, exercise_name, memo, record_id)
            )
        elif category == "meals":
            record_date = request.form.get("record_date")
            meal_type = request.form.get("meal_type")
            food_text = request.form.get("food_text")
            conn.execute(
                "UPDATE meals SET record_date = ?, meal_type = ?, food_text = ? WHERE id = ?",
                (record_date, meal_type, food_text, record_id)
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Error: {e}", 500
    finally:
        conn.close()
    return "OK", 200


@app.route("/delete/<string:category>/<int:record_id>", methods=["POST"])
def delete_record(category, record_id):
    if category not in ["workouts", "meals", "vitals"]:
        return "Invalid category", 400
    
    conn = get_conn()
    try:
        conn.execute(f"DELETE FROM {category} WHERE id = ?", (record_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Error: {e}", 500
    finally:
        conn.close()
    return "OK", 200


ADD_HTML = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>기록 수동 입력</title>
  <style>
    :root { --bg:#0b0f19; --card:#131a26; --line:#243048; --text:#f3f4f6; --muted:#9ca3af;
            --cyan:#06b6d4; --emerald:#10b981; --purple:#8b5cf6; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text);
           font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; padding:20px; }
    .wrap { max-width:640px; margin:0 auto; }
    h1 { font-size:1.4rem; margin:0 0 4px; }
    .sub { color:var(--muted); margin:0 0 18px; font-size:.9rem; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:14px;
            padding:16px 18px; margin-bottom:16px; }
    .card h2 { font-size:1.05rem; margin:0 0 12px; display:flex; align-items:center; gap:8px; }
    .row { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:10px; }
    label { display:flex; flex-direction:column; font-size:.8rem; color:var(--muted); gap:4px; flex:1; min-width:120px; }
    input, select { background:#0b0f19; border:1px solid var(--line); border-radius:8px;
            color:var(--text); padding:9px 10px; font-size:.95rem; }
    button { background:var(--cyan); color:#00121a; border:0; border-radius:9px;
             padding:10px 16px; font-weight:700; font-size:.95rem; cursor:pointer; }
    button:hover { filter:brightness(1.08); }
    .ok { background:rgba(16,185,129,.15); border:1px solid var(--emerald); color:var(--emerald);
          border-radius:10px; padding:10px 14px; margin-bottom:16px; font-weight:600; }
    a.back { color:var(--cyan); text-decoration:none; font-size:.9rem; }
    .badge-w h2 { color:var(--cyan); } .badge-m h2 { color:var(--emerald); } .badge-v h2 { color:var(--purple); }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>📝 기록 수동 입력</h1>
    <p class="sub">웹에서 직접 넣은 기록도 슬랙 입력과 같은 DB에 저장되어 일일/주간 브리핑에 반영됩니다.</p>
    {% if saved %}<div class="ok">✅ {{ saved }} 기록을 저장했습니다.</div>{% endif %}

    <div class="card badge-w">
      <h2>🏋️ 운동</h2>
      <form method="post" action="/add">
        <input type="hidden" name="category" value="workouts">
        <div class="row">
          <label>날짜<input type="date" name="record_date" value="{{ today }}"></label>
          <label>운동명<input name="exercise_name" placeholder="예: 벤치프레스" required></label>
        </div>
        <div class="row">
          <label>무게(kg)<input name="weight_kg" type="number" step="0.1" placeholder="선택"></label>
          <label>횟수<input name="reps" type="number" placeholder="선택"></label>
          <label>세트<input name="sets" type="number" placeholder="선택"></label>
        </div>
        <div class="row"><label>메모<input name="memo" placeholder="선택"></label></div>
        <button type="submit">운동 추가</button>
      </form>
    </div>

    <div class="card badge-m">
      <h2>🍽️ 식단</h2>
      <form method="post" action="/add">
        <input type="hidden" name="category" value="meals">
        <div class="row">
          <label>날짜<input type="date" name="record_date" value="{{ today }}"></label>
          <label>끼니
            <select name="meal_type">
              <option value="아침">아침</option><option value="점심">점심</option>
              <option value="저녁">저녁</option><option value="간식">간식</option>
            </select>
          </label>
        </div>
        <div class="row"><label>음식<input name="food_text" placeholder="예: 닭가슴살 샐러드" required></label></div>
        <div class="row"><label>메모<input name="memo" placeholder="선택"></label></div>
        <button type="submit">식단 추가</button>
      </form>
    </div>

    <div class="card badge-v">
      <h2>❤️ 바이탈</h2>
      <form method="post" action="/add">
        <input type="hidden" name="category" value="vitals">
        <div class="row">
          <label>날짜<input type="date" name="record_date" value="{{ today }}"></label>
          <label>체중(kg)<input name="body_weight_kg" type="number" step="0.1" placeholder="선택"></label>
          <label>수면(시간)<input name="sleep_hours" type="number" step="0.1" placeholder="선택"></label>
        </div>
        <div class="row"><label>컨디션<input name="condition_text" placeholder="선택"></label></div>
        <div class="row"><label>메모<input name="memo" placeholder="선택"></label></div>
        <button type="submit">바이탈 추가</button>
      </form>
    </div>

    <a class="back" href="/">← 대시보드로 돌아가기</a>
  </div>
</body>
</html>
"""


def _to_float(value):
    value = (value or "").strip()
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _to_int(value):
    value = (value or "").strip()
    try:
        return int(float(value)) if value else None
    except ValueError:
        return None


@app.route("/add", methods=["GET", "POST"])
def add_record():
    if request.method == "POST":
        category = request.form.get("category")
        record_date = (request.form.get("record_date") or "").strip() or date.today().isoformat()
        memo = request.form.get("memo") or None
        conn = get_conn()
        try:
            if category == "workouts":
                conn.execute(
                    "INSERT INTO workouts (record_date, exercise_name, weight_kg, reps, sets, memo) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (record_date, (request.form.get("exercise_name") or "").strip(),
                     _to_float(request.form.get("weight_kg")), _to_int(request.form.get("reps")),
                     _to_int(request.form.get("sets")), memo),
                )
                saved = "운동"
            elif category == "meals":
                conn.execute(
                    "INSERT INTO meals (record_date, meal_type, food_text, memo) VALUES (?, ?, ?, ?)",
                    (record_date, request.form.get("meal_type"),
                     (request.form.get("food_text") or "").strip(), memo),
                )
                saved = "식단"
            elif category == "vitals":
                conn.execute(
                    "INSERT INTO vitals (record_date, body_weight_kg, sleep_hours, condition_text, memo) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (record_date, _to_float(request.form.get("body_weight_kg")),
                     _to_float(request.form.get("sleep_hours")),
                     (request.form.get("condition_text") or "").strip() or None, memo),
                )
                saved = "바이탈"
            else:
                return "Invalid category", 400
            conn.commit()
        except Exception as e:
            conn.rollback()
            return f"Error: {e}", 500
        finally:
            conn.close()
        return redirect(url_for("add_record", saved=saved))

    return render_template_string(ADD_HTML, today=date.today().isoformat(),
                                  saved=request.args.get("saved"))


@app.route("/")
def index():
    conn = get_conn()
    workout_count = conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0]
    meal_count = conn.execute("SELECT COUNT(*) FROM meals").fetchone()[0]
    vital_count = conn.execute("SELECT COUNT(*) FROM vitals").fetchone()[0]
    
    latest_weight_row = conn.execute("SELECT body_weight_kg FROM vitals WHERE body_weight_kg IS NOT NULL ORDER BY record_date DESC, id DESC LIMIT 1").fetchone()
    latest_weight = latest_weight_row[0] if latest_weight_row else None
    
    latest_report_row = conn.execute("SELECT report_text FROM reports ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    latest_report = latest_report_row[0] if latest_report_row else None
    
    workouts = conn.execute("SELECT * FROM workouts ORDER BY record_date DESC, id DESC LIMIT 20").fetchall()
    meals = conn.execute("SELECT * FROM meals ORDER BY record_date DESC, id DESC LIMIT 20").fetchall()
    vitals = conn.execute("SELECT * FROM vitals ORDER BY record_date DESC, id DESC LIMIT 20").fetchall()
    
    # 캘린더용 운동 날짜 리스트 추출
    workout_dates = [row['record_date'] for row in conn.execute("SELECT DISTINCT record_date FROM workouts").fetchall()]
    workout_dates_json = json.dumps(workout_dates)
    
    # 연속 운동 스트리크(일수) 계산
    streak_count = calculate_streak(workout_dates)
    
    # 체중 데이터 차트용 추출
    weight_data = conn.execute(
        "SELECT record_date, body_weight_kg FROM vitals WHERE body_weight_kg IS NOT NULL ORDER BY record_date ASC, id ASC"
    ).fetchall()
    weight_labels = [row['record_date'] for row in weight_data]
    weight_values = [row['body_weight_kg'] for row in weight_data]
    weight_labels_json = json.dumps(weight_labels)
    weight_values_json = json.dumps(weight_values)
    
    # 풀업 챌린지 데이터 추출
    pullup_query = """
    SELECT record_date, reps, sets, memo 
    FROM workouts 
    WHERE exercise_name LIKE '%풀업%' 
       OR exercise_name LIKE '%턱걸이%' 
       OR memo LIKE '%풀업%' 
       OR memo LIKE '%턱걸이%'
    """
    pullup_rows = conn.execute(pullup_query).fetchall()
    pullup_by_date = {}
    import re
    for row in pullup_rows:
        d = row['record_date']
        r = row['reps'] or 0
        
        # 만약 reps가 0(None)이면 memo에서 파싱 시도 (하위 호환성)
        if r == 0 and row['memo']:
            m = re.search(r"(\d+)\s*(?:회|개|reps|rep)", row['memo'], re.IGNORECASE)
            if m:
                r = int(m.group(1))
            else:
                fallback_m = re.search(r"(?:풀업|턱걸이)\s*(\d+)", row['memo'])
                if fallback_m:
                    r = int(fallback_m.group(1))
                    
        if r > 0:
            pullup_by_date[d] = max(pullup_by_date.get(d, 0), r)
            
    pullup_pr = max(pullup_by_date.values()) if pullup_by_date else 0
    pullup_history = sorted([{"date": k, "reps": v} for k, v in pullup_by_date.items()], key=lambda x: x['date'], reverse=True)[:5]
    
    conn.close()
    
    return render_template_string(
        HTML,
        workout_count=workout_count,
        meal_count=meal_count,
        vital_count=vital_count,
        latest_weight=latest_weight,
        latest_report=latest_report,
        workouts=workouts,
        meals=meals,
        vitals=vitals,
        workout_dates_json=workout_dates_json,
        streak_count=streak_count,
        weight_labels_json=weight_labels_json,
        weight_values_json=weight_values_json,
        pullup_pr=pullup_pr,
        pullup_history=pullup_history,
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
    