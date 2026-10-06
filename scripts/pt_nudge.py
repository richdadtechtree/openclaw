#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pt_nudge.py — 종국이(GYM종국) '보고 독촉' 톡 (2026-10-06 신설)

무엇을 하나:
  하루 몇 번 정해진 시각(cron)에 오늘 기록을 확인해서, **빠진 게 있을 때만**
  #pt-teacher 에 김종국 말투로 "올려라" 톡을 보낸다. 다 올렸으면 아무 말도 안 한다.

  왜 필요했나: 9/29 형준이 "보고 없으면 타이트하게 보고하라고 해줘" 라고 했고 종국이는
  "알았어" 라고 답했지만, 대화형 AI 는 **먼저 말을 걸 수 없다**(답장만 가능).
  그래서 10/1~10/5 처럼 기록이 비어도 밤 9시 브리핑 전까지 아무 독촉이 없었다.

언제 (기본 cron, scripts/setup-briefing-cron.sh 가 등록):
  10:00  morning  아침 식단 (+ 수면·체중이 없으면 같이 물음)
  13:30  lunch    점심 식단
  18:30  workout  오늘 운동
  20:30  final    21시 브리핑 전 마지막 경고 — 빠진 것 전부

'기록이 있다'의 판단 (둘 중 하나라도 있으면 OK → 독촉 안 함):
  ① PT DB(~/pt_data/pt.db) — 종국이가 대화에서 뽑아 저장한 운동/식단/컨디션
  ② 오늘 #pt-teacher 에 형준이 직접 쓴 메시지 — "아침 …", "점심 …", 운동 이름·kg·세트 등
     (DB 저장이 빠지는 날이 있어도 '올렸는데 또 혼나는' 일이 없게)

강도(타이트함)는 갈수록 세진다:
  • 오늘 이미 독촉했는데 그 뒤로도 답이 없으면 → 한 단계 세게
  • 하루 종일 아무 보고도 없으면 → 마지막 경고는 가장 세게
  • 며칠째 기록이 없으면 → 앞에 "N일째 기록 없음" 을 붙임
  • 오늘 "아프다/병원/몸살/부상" 이라고 했으면 운동 독촉은 안 함(힘든 것 ≠ 아픈 것)
  • 오늘 "잔소리 쉬어/그만" 이라고 했으면 그날은 독촉 안 함

사용:
  python3 pt_nudge.py morning|lunch|workout|final
  옵션:
    --dry-run           보내지 않고 무엇을 보낼지만 출력(발송 기록도 안 남김)
    --now 2026-10-06T10:00   시각 지정(검사용, 기본: 지금 KST)
    --force             같은 날 같은 시간대에 이미 보냈어도 다시 보냄

필요 (.env — pt_briefing.py 와 같음):
  SLACK_BOT_TOKEN_KEEPGOING  종국이 봇 토큰 (chat:write, 채널 읽기 groups:history)
  SLACK_KEEPGOING_CHANNEL    기본 C0BMN9FN073 (#pt-teacher)
  PT_SLACK_USER              형준 슬랙 ID, 기본 U0BMLMRHAQL (멘션해서 폰 알림이 울리게)
  PT_NUDGE=off               전부 끄기
표준 라이브러리만 사용 → 서버 시스템 python3 로 실행 가능(requests 불필요).
"""
import os
import re
import sys
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pt_briefing as pb   # .env 읽기·DB·슬랙 호출·날짜별 문장 고르기(pick)를 같이 쓴다

KST = ZoneInfo("Asia/Seoul")
DEFAULT_USER = "U0BMLMRHAQL"
SLOTS = ("morning", "lunch", "workout", "final")

# ── 형준이 메시지에서 '올렸다'를 알아보는 낱말 ────────────────────────────────
RE_MEAL = {
    "아침": re.compile(r"아침|조식|모닝"),
    "점심": re.compile(r"점심|중식|런치"),
    "저녁": re.compile(r"저녁|석식|야식|디너"),
}
RE_WORKOUT = re.compile(
    r"운동|헬스|PT|피티|스쿼트|데드|벤치|프레스|레그|로우|풀업|턱걸이|푸시업|팔굽|런지|"
    r"컬|익스텐션|랫풀|덤벨|바벨|어덕션|이너\s*싸이|플랭크|복근|"
    r"러닝|런닝|달리기|조깅|걷기|산책|등산|테니스|수영|자전거|사이클|요가|필라테스|"
    r"\d+\s*(?:세트|회|km)|\d+\s*(?:kg|키로)?\s*[x×*]\s*\d+", re.I)
# ⚠️ 'kg' 만으로는 운동으로 안 친다 — "체중 74.7kg" 이 운동으로 잡히면 안 되니까. 무게×횟수(160×10)는 운동.
RE_VITAL = re.compile(r"수면|잤|잠을|\d+\s*시간\s*잠|체중|몸무게")
RE_SICK = re.compile(r"아프|아파|통증|병원|몸살|부상|다쳤|다침|감기|열이|찌릿")
RE_MUTE = re.compile(r"잔소리\s*(?:쉬어|그만|꺼|멈춰|스톱|오프)|독촉\s*(?:쉬어|그만|꺼)")


# ── 기록 모으기 ───────────────────────────────────────────────────────────────
def fetch_user_messages(since):
    """since(KST) 이후 #pt-teacher 에 형준이 직접 쓴 메시지 [(ts, text)] — 오늘 판단 + 잠수 일수 계산용.
    읽기 실패(권한·네트워크)면 None → DB 기록만으로 판단."""
    token = pb.slack_token()
    if not token:
        return None
    user = os.getenv("PT_SLACK_USER") or DEFAULT_USER
    out, cursor = [], None
    try:
        for _ in range(5):   # 하루치면 한두 쪽이면 충분, 혹시 몰라 5쪽까지만
            params = {"channel": pb.slack_channel(), "oldest": f"{since.timestamp():.6f}",
                      "limit": 200}
            if cursor:
                params["cursor"] = cursor
            r = pb.slack_call("conversations.history", token, params=params)
            if not r.get("ok"):
                print(f"[Warn] 채널 읽기 실패: {r.get('error')} → DB 기록만으로 판단")
                return None
            for m in r.get("messages", []):
                if m.get("user") != user or m.get("bot_id"):
                    continue
                text = m.get("text") or ""
                for f in m.get("files") or []:          # 사진만 올린 경우 파일 이름도 단서
                    text += " " + (f.get("title") or f.get("name") or "")
                out.append((float(m.get("ts", 0)), text))
            cursor = (r.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
    except Exception as ex:
        print(f"[Warn] 채널 읽기 오류({ex}) → DB 기록만으로 판단")
        return None
    return sorted(out)


def gather(con, day, msgs):
    """오늘 무엇이 올라왔는지 정리."""
    d = day.isoformat()
    diet = pb.q(con, "SELECT meal, items FROM diet WHERE date=?", (d,))
    workouts = pb.q(con, "SELECT exercise FROM workouts WHERE date=?", (d,))
    vital = pb.q_one(con, "SELECT weight_kg, sleep_hours FROM vitals WHERE date=?", (d,))
    texts = [t for _, t in (msgs or [])]
    joined = "\n".join(texts)

    meals = {}
    for name, rx in RE_MEAL.items():
        in_db = any(rx.search((x.get("meal") or "")) for x in diet)
        meals[name] = in_db or any(rx.search(t) for t in texts)
    return {
        "meals": meals,
        "any_diet": bool(diet) or any(meals.values()),
        "workout": bool(workouts) or any(RE_WORKOUT.search(t) for t in texts),
        "vital": bool(vital and (vital.get("sleep_hours") or vital.get("weight_kg")))
                 or any(RE_VITAL.search(t) for t in texts),
        "sick": bool(RE_SICK.search(joined)),
        "mute": bool(RE_MUTE.search(joined)),
        "any_msg": bool(texts),
        "msgs_known": msgs is not None,
    }


def silent_days(con, day, all_msgs):
    """어제부터 거꾸로, 아무 기록도 없는 날이 며칠 이어졌나 (최대 14).
    DB 기록(운동·식단·컨디션) 또는 그날 형준이 채널에 쓴 메시지가 하나라도 있으면 '기록 있음'."""
    msg_days = {datetime.fromtimestamp(t, KST).date() for t, _ in (all_msgs or [])}
    n = 0
    for i in range(1, 15):
        dd = day - timedelta(days=i)
        d = dd.isoformat()
        has = (dd in msg_days or pb.q_one(con, "SELECT 1 AS x FROM workouts WHERE date=? LIMIT 1", (d,))
               or pb.q_one(con, "SELECT 1 AS x FROM diet WHERE date=? LIMIT 1", (d,))
               or pb.q_one(con, "SELECT 1 AS x FROM vitals WHERE date=? LIMIT 1", (d,)))
        if has:
            break
        n += 1
    return n


# ── 오늘 보낸 독촉 기록 (중복 방지 + 강도 올리기) ─────────────────────────────
def ensure_table(con):
    con.execute("CREATE TABLE IF NOT EXISTS pt_nudges ("
                "date TEXT NOT NULL, slot TEXT NOT NULL, sent_at REAL NOT NULL, "
                "text TEXT, PRIMARY KEY (date, slot))")
    con.commit()


def ignored_count(con, day, msgs):
    """오늘 보낸 독촉 중, 그 뒤로 형준이 한마디도 안 한 것의 개수."""
    sent = pb.q(con, "SELECT sent_at FROM pt_nudges WHERE date=? ORDER BY sent_at",
                (day.isoformat(),))
    if msgs is None:
        return 0      # 채널을 못 읽으면 '무시당했다'고 단정하지 않는다
    last_msg = max((ts for ts, _ in msgs), default=0)
    return sum(1 for s in sent if s["sent_at"] > last_msg)


# ── 김종국 말투 문장 창고 ─────────────────────────────────────────────────────
# 규칙(CueEngine.md): 짧게, 시그니처는 1~2개, 반말 + ㅎ, 가족 동기부여는 가끔.
# 단계 0 = 첫 독촉(가볍게), 1 = 답 없음(세게), 2 = 하루 종일 무소식(가장 세게).
MORNING = [
    ["형준아 ㅎ 아침 먹었어? 뭐 먹었는지 한 줄 올려. 단백질부터 말해 ㅎ",
     "아침 보고 아직이다 ㅎ 굶은 거 아니지? 뭐 먹었는지 올려.",
     "좋은 아침 ㅎ 아침 뭐 먹었어? 계란이라도 들어갔으면 칭찬해 줄게 ㅎ"],
    ["아침 보고 아직도 없다. 굶은 거야, 안 올린 거야? 둘 다 안 돼 ㅎ 지금 한 줄.",
     "형준아 ㅎ 아침 먹은 거 말하라니까 ㅎ 굶지 마 제발. 양 줄이지 말고 종류만 바꾸는 거야."],
]
LUNCH = [
    ["점심 뭐 먹었어? 사진이든 한 줄이든 올려 ㅎ 먹는 것까지가 운동이야.",
     "점심 보고 들어와야지 ㅎ 단백질 뭐 먹었는지 그거부터.",
     "점심시간 지났다 ㅎ 뭐 먹었는지 올려. 종류만 바꿔도 몸 바뀐다."],
    ["아침도 점심도 보고가 없어. ㅎ 형준아, 지금 바로 올려. 먹은 거 한 줄이면 돼.",
     "오전 내내 조용하다 ㅎ 아침·점심 뭐 먹었어? 안 올리면 굶은 걸로 친다 ㅎ"],
]
WORKOUT = [
    ["오늘 운동 몇 시에 해? 시간부터 정해. 40분이면 충분해 ㅎ",
     "오늘 운동 계획 말해 봐 ㅎ 몇 시, 어디, 무슨 부위. 그것만.",
     "퇴근 각이지? ㅎ 오늘 운동 몇 시야? 정하면 하는 거고 안 정하면 안 하는 거야."],
    ["아직 운동 보고 없다. 퇴근했으면 바로 가 ㅎ 시간 없어? 폰 보는 시간은 있고? ㅎ",
     "운동 소식이 없네 ㅎ 체육관 못 가면 집에서 스쿼트 20개, 푸시업 20개. 하고 올려.",
     "말할 시간에 하나 더 하는 거야 ㅎ 오늘 운동 아직이면 지금 신발부터 신어."],
]
WORKOUT_TRAVEL = ("밖이라도 괜찮아 ㅎ 아이들이랑 뛰어노는 것도 운동이야. "
                  "대신 스쿼트 20개는 하고 자 ㅎ 했으면 올리고.")
FINAL = [
    ["30분 뒤에 오늘 브리핑 나간다 ㅎ 지금 안 올리면 '기록 없음'으로 찍혀. 빠진 거: {missing}",
     "브리핑 30분 전이다 ㅎ {missing} — 이거 올리고 마무리하자."],
    ["형준아. 30분 뒤 브리핑이야. {missing} 아직이다. 했으면 올리고, 안 했으면 지금 해 ㅎ 변명 말고.",
     "오늘 독촉 그냥 넘겼지? ㅎ {missing}. 30분 남았다. 지금 올려."],
    ["형준아. 오늘 하루 종일 아무 보고가 없다. 살아있지? ㅎ 혼내려는 거 아니야. "
     "운동이든 밥이든 한 줄이면 돼. 지금.",
     "오늘 보고 0건이다 ㅎ 늘 컨디션 좋은 사람은 없어. 그래도 한 줄은 올리고 자. "
     "건강한 아빠가 최고의 아빠야 ㅎ"],
]
VITAL_ASK = "그리고 어젯밤 몇 시간 잤어? 체중도 ㅎ"
SICK_NOTE = "아픈 데 있으면 운동은 쉬어. 힘든 거랑 아픈 건 달라. 대신 밥은 제대로 먹고 올려 ㅎ"


def build(slot, st, ignored, gone_days, now):
    """보낼 문장을 만든다. 보낼 게 없으면 None."""
    day = now.date()
    level = min(ignored, 1)
    meals = st["meals"]

    if slot == "morning":
        if meals["아침"]:
            body = VITAL_ASK if not st["vital"] else None
        else:
            body = pb.pick(MORNING[level], day)
            if not st["vital"]:
                body += "\n" + VITAL_ASK
    elif slot == "lunch":
        if meals["점심"]:
            return None
        # 아침도 없으면 바로 센 쪽으로
        lv = 1 if (not meals["아침"] or ignored) else 0
        body = pb.pick(LUNCH[lv], day)
    elif slot == "workout":
        if st["workout"]:
            return None
        if st["sick"]:
            return None          # 아프다고 한 날은 운동 독촉 안 함
        body = pb.pick(WORKOUT[level], day, 1)
    else:   # final
        missing = []
        if not st["workout"] and not st["sick"]:
            missing.append("운동")
        if not st["any_diet"]:
            missing.append("오늘 먹은 거")
        elif not meals["저녁"]:
            missing.append("저녁")
        if not missing:
            return None
        if st["msgs_known"] and not st["any_msg"]:
            lv = 2               # 하루 종일 무소식
        else:
            lv = min(ignored, 1)
        body = pb.pick(FINAL[lv], day, 2).format(missing=" · ".join(missing))
        if st["sick"]:
            body += "\n" + SICK_NOTE

    if not body:
        return None
    head = ""
    if gone_days >= 2 and not st["any_msg"]:
        head = f"{gone_days}일째 기록이 없다 ㅎ 잠수는 여기까지. "
    user = os.getenv("PT_SLACK_USER") or DEFAULT_USER
    return f"<@{user}> {head}{body}"


def main():
    args = sys.argv[1:]
    slot = next((a for a in args if a in SLOTS), None)
    if not slot:
        print(__doc__)
        sys.exit(2)
    dry = "--dry-run" in args
    force = "--force" in args
    now = datetime.now(KST)
    if "--now" in args:
        now = datetime.fromisoformat(args[args.index("--now") + 1]).replace(tzinfo=KST)

    pb.load_env()
    if (os.getenv("PT_NUDGE") or "").lower() in ("off", "0", "false", "no"):
        print("[Skip] PT_NUDGE=off — 독촉 꺼짐")
        return

    day = now.date()
    day_start = datetime.combine(day, dtime(0, 0), tzinfo=KST)
    con = pb.get_db()
    ensure_table(con)

    if not force and pb.q_one(con, "SELECT 1 AS x FROM pt_nudges WHERE date=? AND slot=?",
                              (day.isoformat(), slot)):
        print(f"[Skip] {day} {slot} 독촉은 이미 보냄")
        con.close()
        return

    all_msgs = fetch_user_messages(day_start - timedelta(days=14))
    msgs = None if all_msgs is None else [m for m in all_msgs if m[0] >= day_start.timestamp()]
    st = gather(con, day, msgs)
    if st["mute"]:
        print("[Skip] 오늘 '잔소리 쉬어' 요청 있음")
        con.close()
        return

    text = build(slot, st, ignored_count(con, day, msgs), silent_days(con, day, all_msgs), now)
    if not text:
        print(f"[OK] {slot}: 다 올렸음 → 독촉 안 함 ({st})")
        con.close()
        return

    print(f"[{slot}] 보낼 내용:\n{text}")
    if dry:
        print("(--dry-run: 보내지 않음)")
        con.close()
        return

    # 먼저 자리표(중복 방지) → 보내고 → 실패하면 반납
    cur = con.execute("INSERT OR IGNORE INTO pt_nudges (date, slot, sent_at, text) VALUES (?,?,?,?)",
                      (day.isoformat(), slot, now.timestamp(), text))
    con.commit()
    if cur.rowcount != 1 and not force:
        print("[Skip] 다른 실행이 방금 보냄")
        con.close()
        return
    if force:
        con.execute("UPDATE pt_nudges SET sent_at=?, text=? WHERE date=? AND slot=?",
                    (now.timestamp(), text, day.isoformat(), slot))
        con.commit()
    if pb.post_slack(text):
        print("✅ 슬랙 독촉 전송 완료")
    else:
        con.execute("DELETE FROM pt_nudges WHERE date=? AND slot=?", (day.isoformat(), slot))
        con.commit()
    con.close()


if __name__ == "__main__":
    main()
