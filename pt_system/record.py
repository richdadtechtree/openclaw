#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pt_system/record.py — 운동/식단/바이탈 기록 CLI (슬랙 PT 에이전트가 exec 로 호출)

슬랙에서 사용자가 자연어로 입력하면, PT 에이전트(LLM)가 내용을 구조화해서 이 스크립트를
호출한다. 저장 후 [기록 완료] 요약(오늘 기준 개수)을 출력하므로 에이전트가 그대로 답장에
활용할 수 있다. 표준 라이브러리만 사용.

── 개별 기록 ────────────────────────────────────────────────
  python3 pt_system/record.py workout --detail "벤치 5x5, 스쿼트 5x5" \
          [--type 웨이트] [--duration 45] [--intensity 보통] [--date 2026-08-07] [--note ..]
  python3 pt_system/record.py meal --meal 점심 --items "제육덮밥" \
          [--kcal 700] [--protein 30] [--note ..] [--date ..]
  python3 pt_system/record.py vital [--weight 72.4] [--sleep 6.5] \
          [--condition "약간 피곤"] [--mood 보통] [--note ..] [--date ..]

── 한 번에 여러 건 (에이전트 권장) ──────────────────────────
  python3 pt_system/record.py json '{"date":"2026-08-07",
      "workouts":[{"type":"웨이트","detail":"벤치 5x5","duration_min":45}],
      "meals":[{"meal":"점심","items":"제육덮밥","kcal":700,"protein_g":30}],
      "vitals":[{"weight_kg":72.4,"sleep_h":6.5,"condition":"피곤"}],
      "raw":"오늘 웨이트 45분 하고 점심 제육덮밥 먹음. 몸무게 72.4"}'

  (stdin 으로도 가능: echo '<json>' | python3 pt_system/record.py json -)

옵션: --source (기본 slack), --quiet (요약 출력 생략)
출력 마지막 줄은 항상 `RESULT_JSON: {...}` 형태(에이전트 파싱용).
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402


def _to_int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def apply_batch(con, payload, source="slack"):
    """dict payload -> 삽입. 반환: {'workouts':n,'meals':n,'vitals':n}"""
    date = payload.get("date")
    raw = payload.get("raw")
    n = {"workouts": 0, "meals": 0, "vitals": 0}
    for w in payload.get("workouts", []) or []:
        db.add_workout(con, date=w.get("date", date), type=w.get("type"),
                       detail=w.get("detail"), duration_min=_to_int(w.get("duration_min")),
                       intensity=w.get("intensity"), note=w.get("note"),
                       source=source, raw=w.get("raw", raw))
        n["workouts"] += 1
    for m in payload.get("meals", []) or []:
        db.add_meal(con, date=m.get("date", date), meal=m.get("meal"),
                    items=m.get("items"), kcal=_to_int(m.get("kcal")),
                    protein_g=_to_float(m.get("protein_g")), note=m.get("note"),
                    source=source, raw=m.get("raw", raw))
        n["meals"] += 1
    for v in payload.get("vitals", []) or []:
        db.add_vital(con, date=v.get("date", date), weight_kg=_to_float(v.get("weight_kg")),
                     sleep_h=_to_float(v.get("sleep_h")), condition=v.get("condition"),
                     mood=v.get("mood"), note=v.get("note"),
                     source=source, raw=v.get("raw", raw))
        n["vitals"] += 1
    if raw:
        kinds = [k for k in n if n[k]]
        db.log_ingest(con, source=source, text=raw,
                      parsed_kind=",".join(kinds) if kinds else "none")
    return n, (date or db.today_str())


def print_summary(con, added, date, quiet=False):
    c = db.counts_for_date(con, date)
    vital_state = "저장됨" if c["vitals"] else "없음"
    if not quiet:
        print("[기록 완료]")
        print(f"- 운동: {c['workouts']}개")
        print(f"- 식단: {c['meals']}개")
        print(f"- 바이탈: {vital_state}")
        print(f"  (이번 저장분 — 운동 {added['workouts']} / 식단 {added['meals']} / "
              f"바이탈 {added['vitals']}, 날짜 {date})")
    result = {"ok": True, "date": date, "added": added, "today_totals": c}
    print("RESULT_JSON: " + json.dumps(result, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="PT 기록 CLI")
    ap.add_argument("--source", default="slack")
    ap.add_argument("--quiet", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pw = sub.add_parser("workout")
    pw.add_argument("--type"); pw.add_argument("--detail")
    pw.add_argument("--duration", type=int); pw.add_argument("--intensity")
    pw.add_argument("--note"); pw.add_argument("--date"); pw.add_argument("--raw")

    pm = sub.add_parser("meal")
    pm.add_argument("--meal"); pm.add_argument("--items")
    pm.add_argument("--kcal", type=int); pm.add_argument("--protein", type=float)
    pm.add_argument("--note"); pm.add_argument("--date"); pm.add_argument("--raw")

    pv = sub.add_parser("vital")
    pv.add_argument("--weight", type=float); pv.add_argument("--sleep", type=float)
    pv.add_argument("--condition"); pv.add_argument("--mood")
    pv.add_argument("--note"); pv.add_argument("--date"); pv.add_argument("--raw")

    pj = sub.add_parser("json")
    pj.add_argument("data", help="JSON 문자열 또는 '-' (stdin)")

    args = ap.parse_args()
    db.init_db()
    con = db.connect()
    try:
        if args.cmd == "json":
            text = sys.stdin.read() if args.data == "-" else args.data
            payload = json.loads(text)
        elif args.cmd == "workout":
            payload = {"date": args.date, "raw": args.raw,
                       "workouts": [{"type": args.type, "detail": args.detail,
                                     "duration_min": args.duration, "intensity": args.intensity,
                                     "note": args.note}]}
        elif args.cmd == "meal":
            payload = {"date": args.date, "raw": args.raw,
                       "meals": [{"meal": args.meal, "items": args.items,
                                  "kcal": args.kcal, "protein_g": args.protein,
                                  "note": args.note}]}
        elif args.cmd == "vital":
            payload = {"date": args.date, "raw": args.raw,
                       "vitals": [{"weight_kg": args.weight, "sleep_h": args.sleep,
                                   "condition": args.condition, "mood": args.mood,
                                   "note": args.note}]}
        else:  # pragma: no cover
            ap.error("알 수 없는 명령")
            return
        added, date = apply_batch(con, payload, source=args.source)
        con.commit()
        print_summary(con, added, date, quiet=args.quiet)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"JSON 파싱 실패: {e}"}, ensure_ascii=False))
        sys.exit(1)
    finally:
        con.close()


if __name__ == "__main__":
    main()
