#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pt_system/app.py — PT 대시보드 웹서버 (stdlib http.server 전용, 무설치)

DB(pt.sqlite)를 읽어 운동/식단/체중 현황을 웹으로 보여준다. FastAPI/uvicorn 등
외부 패키지 없이 표준 라이브러리만으로 동작하므로 서버에 그대로 올려 실행하면 된다.
nginx 뒤에 두어 mystatus-btr.duckdns.org 로 서비스한다.

실행:
  python3 pt_system/app.py                 # 0.0.0.0:8770
  PT_DASH_PORT=8770 python3 pt_system/app.py
  PT_DB_PATH=~/.openclaw/pt_system/pt.sqlite python3 pt_system/app.py

엔드포인트:
  GET /               HTML 대시보드
  GET /api/summary    최근 7/30일 집계 JSON
  GET /api/records?type=workout|meal|vital&limit=50   최근 기록 JSON
  GET /healthz        상태 확인
"""
import os
import sys
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

PORT = int(os.getenv("PT_DASH_PORT", "8770"))
HOST = os.getenv("PT_DASH_HOST", "0.0.0.0")


# ── 데이터 조회 ──────────────────────────────────────────────
def build_summary():
    con = db.connect(readonly=True)
    try:
        wk = db.weekly_stats(con, days=7)
        mo = db.weekly_stats(con, days=30)
        since = db.days_since_workout(con)
        lw = db.latest_weight(con)
        wseries = db.weight_series(con, days=30)
        return {
            "generated": db.now_kst().isoformat(timespec="seconds"),
            "today": db.today_str(),
            "week": wk, "month": mo,
            "days_since_workout": since,
            "latest_weight": lw,
            "weight_series": wseries,
        }
    finally:
        con.close()


def build_records(kind, limit):
    table = {"workout": "workouts", "meal": "meals", "vital": "vitals"}.get(kind)
    if not table:
        return []
    con = db.connect(readonly=True)
    try:
        return db.recent(con, table, limit=limit)
    finally:
        con.close()


# ── HTML ─────────────────────────────────────────────────────
def esc(s):
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def sparkline_svg(series, w=520, h=120, pad=18):
    """체중 추이 인라인 SVG (외부 라이브러리 없음)."""
    pts = [(p["date"], p["weight_kg"]) for p in series if p.get("weight_kg") is not None]
    if len(pts) < 2:
        return '<p class="muted">체중 데이터가 2개 이상 쌓이면 추이 그래프가 표시됩니다.</p>'
    ys = [v for _, v in pts]
    ymin, ymax = min(ys), max(ys)
    if ymax == ymin:
        ymax += 1
    n = len(pts)

    def X(i):
        return pad + (w - 2 * pad) * i / (n - 1)

    def Y(v):
        return pad + (h - 2 * pad) * (1 - (v - ymin) / (ymax - ymin))

    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(pts))
    dots = "".join(
        f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3" class="dot"><title>{esc(d)}: {v:g}kg</title></circle>'
        for i, (d, v) in enumerate(pts))
    first_lbl = f'<text x="{pad}" y="{h-4}" class="axis">{esc(pts[0][0][5:])}</text>'
    last_lbl = f'<text x="{w-pad}" y="{h-4}" text-anchor="end" class="axis">{esc(pts[-1][0][5:])}</text>'
    max_lbl = f'<text x="{pad}" y="{pad}" class="axis">{ymax:g}kg</text>'
    min_lbl = f'<text x="{pad}" y="{h-pad+2}" class="axis">{ymin:g}kg</text>'
    return f'''<svg viewBox="0 0 {w} {h}" class="spark" role="img" aria-label="체중 추이">
  <polyline points="{line}" fill="none" class="sparkline"/>
  {dots}{first_lbl}{last_lbl}{max_lbl}{min_lbl}
</svg>'''


def kcal_line(m):
    bits = []
    if m.get("kcal"):
        bits.append(f"{m['kcal']}kcal")
    if m.get("protein_g"):
        bits.append(f"단백질 {m['protein_g']:g}g")
    return " · ".join(bits)


def render_html():
    s = build_summary()
    wk, mo = s["week"], s["month"]
    since = s["days_since_workout"]
    lw = s["latest_weight"]

    # KPI 카드
    since_txt = "오늘 완료" if since == 0 else (
        f"{since}일 전" if since is not None else "기록 없음")
    since_cls = "ok" if (since is not None and since == 0) else (
        "warn" if (since is not None and since >= 2) else "")
    weight_txt = f"{lw['weight_kg']:g} kg" if lw else "—"
    weight_sub = f"{lw['date']}" if lw else "체중 기록 없음"
    week_goal_cls = "ok" if wk["workout_days"] >= 3 else "warn"

    recent_w = build_records("workout", 8)
    recent_m = build_records("meal", 8)

    def row_workout(w):
        meta = []
        if w.get("duration_min"):
            meta.append(f"{w['duration_min']}분")
        if w.get("intensity"):
            meta.append(esc(w["intensity"]))
        return (f'<tr><td class="d">{esc(w["date"])}</td>'
                f'<td>{esc(w.get("type") or "운동")}</td>'
                f'<td>{esc(w.get("detail") or "")}</td>'
                f'<td class="num">{esc(" · ".join(meta))}</td></tr>')

    def row_meal(m):
        return (f'<tr><td class="d">{esc(m["date"])}</td>'
                f'<td>{esc(m.get("meal") or "식사")}</td>'
                f'<td>{esc(m.get("items") or "")}</td>'
                f'<td class="num">{esc(kcal_line(m))}</td></tr>')

    workouts_rows = "".join(row_workout(w) for w in recent_w) or \
        '<tr><td colspan="4" class="muted">운동 기록이 아직 없습니다.</td></tr>'
    meals_rows = "".join(row_meal(m) for m in recent_m) or \
        '<tr><td colspan="4" class="muted">식단 기록이 아직 없습니다.</td></tr>'

    weight_diff = ""
    if wk["weight_first"] is not None and wk["weight_last"] is not None:
        d = round(wk["weight_last"] - wk["weight_first"], 1)
        arrow = "▼" if d < 0 else ("▲" if d > 0 else "―")
        weight_diff = f'<span class="diff">{arrow}{abs(d):g}kg / 7일</span>'

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI PT 대시보드</title>
<style>
  :root {{
    --bg:#f6f7f9; --card:#ffffff; --fg:#1c2024; --muted:#6b7280;
    --line:#e6e8eb; --accent:#2f6df6; --ok:#12855b; --warn:#c2410c;
    --shadow:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#0f1113; --card:#181b1f; --fg:#e8eaed; --muted:#9aa1a9;
      --line:#2a2e34; --accent:#5b8cff; --ok:#3fbb87; --warn:#f6864b;
      --shadow:0 1px 3px rgba(0,0,0,.4);
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
    line-height:1.5; }}
  .wrap {{ max-width:820px; margin:0 auto; padding:20px 16px 60px; }}
  header {{ display:flex; align-items:baseline; justify-content:space-between; flex-wrap:wrap; gap:8px; }}
  h1 {{ font-size:20px; margin:0; }}
  .gen {{ color:var(--muted); font-size:12px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:18px 0; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; box-shadow:var(--shadow); }}
  .card .label {{ color:var(--muted); font-size:12px; margin-bottom:6px; }}
  .card .value {{ font-size:22px; font-weight:700; }}
  .card .sub {{ color:var(--muted); font-size:12px; margin-top:4px; }}
  .value.ok {{ color:var(--ok); }} .value.warn {{ color:var(--warn); }}
  .diff {{ font-size:12px; color:var(--muted); margin-left:6px; }}
  section {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin:14px 0; box-shadow:var(--shadow); }}
  section h2 {{ font-size:15px; margin:0 0 10px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th, td {{ text-align:left; padding:8px 6px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ color:var(--muted); font-weight:600; font-size:12px; }}
  td.d {{ color:var(--muted); white-space:nowrap; font-size:12px; }}
  td.num {{ white-space:nowrap; color:var(--muted); }}
  .muted {{ color:var(--muted); }}
  .spark {{ width:100%; height:auto; }}
  .sparkline {{ stroke:var(--accent); stroke-width:2.2; }}
  .dot {{ fill:var(--accent); }}
  .axis {{ fill:var(--muted); font-size:10px; }}
  .tblwrap {{ overflow-x:auto; }}
  footer {{ color:var(--muted); font-size:12px; text-align:center; margin-top:24px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🏋️ AI PT 대시보드</h1>
    <span class="gen">업데이트 {esc(s['generated'])} · 오늘 {esc(s['today'])}</span>
  </header>

  <div class="cards">
    <div class="card">
      <div class="label">이번 주 운동</div>
      <div class="value {week_goal_cls}">{wk['workout_days']}/7일</div>
      <div class="sub">{wk['workout_count']}세션 · {wk['workout_minutes']}분</div>
    </div>
    <div class="card">
      <div class="label">마지막 운동</div>
      <div class="value {since_cls}">{since_txt}</div>
      <div class="sub">목표 주 3회</div>
    </div>
    <div class="card">
      <div class="label">최근 체중</div>
      <div class="value">{weight_txt}</div>
      <div class="sub">{esc(weight_sub)} {weight_diff}</div>
    </div>
    <div class="card">
      <div class="label">최근 30일 운동</div>
      <div class="value">{mo['workout_days']}일</div>
      <div class="sub">{mo['workout_minutes']}분 · 식단 {mo['meal_count']}건</div>
    </div>
  </div>

  <section>
    <h2>체중 추이 (30일)</h2>
    {sparkline_svg(s['weight_series'])}
  </section>

  <section>
    <h2>최근 운동</h2>
    <div class="tblwrap"><table>
      <thead><tr><th>날짜</th><th>종류</th><th>내용</th><th>시간/강도</th></tr></thead>
      <tbody>{workouts_rows}</tbody>
    </table></div>
  </section>

  <section>
    <h2>최근 식단</h2>
    <div class="tblwrap"><table>
      <thead><tr><th>날짜</th><th>끼니</th><th>내용</th><th>영양</th></tr></thead>
      <tbody>{meals_rows}</tbody>
    </table></div>
  </section>

  <footer>openclaw · PT tracker · 데이터 출처: pt.sqlite</footer>
</div>
</body>
</html>"""


# ── HTTP 핸들러 ──────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "PTDash/1.0"

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str),
                   "application/json; charset=utf-8")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                self._send(200, render_html())
            elif u.path == "/healthz":
                self._json({"ok": True, "time": db.now_kst().isoformat(timespec="seconds")})
            elif u.path == "/api/summary":
                self._json(build_summary())
            elif u.path == "/api/records":
                kind = (q.get("type", ["workout"])[0]).rstrip("s")
                limit = min(int(q.get("limit", ["50"])[0]), 500)
                self._json({"type": kind, "records": build_records(kind, limit)})
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            self._json({"ok": False, "error": repr(e)}, 500)

    def log_message(self, fmt, *args):  # 조용히
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    db.init_db()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"PT 대시보드 실행: http://{HOST}:{PORT}  (DB={db.db_path()})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
