# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## 🏋️ PT 기록 시스템 (pt_system) — 필독 · 반드시 사용

채널은 **슬랙**이다. 사용자가 슬랙으로 운동/식단/체중/수면/컨디션을 말하면,
너는 그 내용을 **구조화해서 DB에 저장**해야 한다. 저장은 `exec` 툴로 아래 스크립트를
실행한다. **경로 기준(cwd)은 `~/.openclaw`** (뉴스 브리핑에서 `python workspace/...` 를
쓰던 것과 동일). 파이썬은 `python3`.

### 저장 (한 번에 여러 건 권장 — json 모드)

사용자 한 메시지에 운동·식단·바이탈이 섞여 있으면 **한 번의 호출**로 저장한다.
`raw` 에는 사용자의 원문을 그대로 넣는다(나중 검증·백필용).

```
python3 pt_system/record.py json '{
  "date":"2026-08-07",
  "workouts":[{"type":"웨이트","detail":"벤치 5x5, 스쿼트 5x5","duration_min":45,"intensity":"보통"}],
  "meals":[{"meal":"점심","items":"제육덮밥","kcal":700,"protein_g":30}],
  "vitals":[{"weight_kg":72.4,"sleep_h":6.5,"condition":"약간 피곤"}],
  "raw":"오늘 웨이트 45분 하고 점심 제육덮밥. 몸무게 72.4, 6시간반 잠"
}'
```

- `date` 생략 시 오늘(KST). 사용자가 "어제"라고 하면 해당 날짜로 넣는다.
- 모르는 값은 넣지 마라(추측 금지). 수치가 없으면 그 필드는 생략.
- 개별 저장도 가능: `record.py workout --detail "..." --duration 40` /
  `record.py meal --meal 점심 --items "..."` / `record.py vital --weight 72.4 --sleep 7`

### 저장 후 답장

스크립트 출력의 `[기록 완료]` 요약(오늘 기준 개수)을 그대로 활용해 짧게 답한다.
마지막 줄 `RESULT_JSON: {...}` 는 파싱용 데이터니 사용자에게 노출하지 마라.

형식(SOUL/USER 규칙과 동일):
```
[기록 완료]
- 운동: N개
- 식단: N개
- 바이탈: 저장됨/없음
- 오늘의 한마디: (한두 문장, 네 페르소나로)
```

### 브리핑 (요청 시)

- 일간: `python3 pt_system/briefing.py daily`
- 주간: `python3 pt_system/briefing.py weekly`

출력(규칙 기반 집계)을 바탕으로 네 코칭 멘트를 덧붙여 답한다. 집계 수치는 스크립트를
신뢰한다(직접 계산하지 마라).

### 대시보드

웹 대시보드는 <http://mystatus-btr.duckdns.org/> 에서 같은 DB(`pt_system/pt.sqlite`)를
읽어 보여준다. "대시보드 보여줘" 요청엔 이 링크를 안내한다.

### 경계

기록은 이 시스템에만 저장한다. 텔레그램은 더 이상 쓰지 않는다.

## Related

- [Agent workspace](/concepts/agent-workspace)
