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

## 🏋️ PT 기록 저장 — 반드시 이 스크립트로 (필독)

채널은 **슬랙**이다. 사용자가 운동/식단/체중/수면/컨디션을 말하면, 그 **원문을 그대로**
아래 스크립트에 넘겨 DB(`/home/ubuntu/pt_system/pt_data.db`)에 저장한다. 이 DB는 웹 대시보드
(`mystatus-btr.duckdns.org`)가 읽는 바로 그 DB다.

**저장 (exec 툴로 실행):**
```
/home/ubuntu/pt_system/venv/bin/python /home/ubuntu/pt_system/scripts/save_message.py --source slack "<사용자 원문 그대로>"
```
- ⚠️ 반드시 **절대경로 + pt_system venv 파이썬**을 써라. `python3 pt_system/record.py` 같은
  상대경로/다른 스크립트는 없다(예전 실수). 위 경로 그대로 실행한다.
- 사용자 메시지를 **재가공하지 말고 원문**을 큰따옴표로 감싸 넘겨라. 스크립트가 운동/식단/
  바이탈을 알아서 파싱해 저장한다. (여러 줄이면 그대로, 줄바꿈 포함)
- 스크립트 stdout 의 `[기록 완료] - 운동:N - 식단:N - 바이탈:...` 이 **실제 저장 결과**다.
  이 수치를 **지어내지 말고** 스크립트 출력 그대로 사용한 뒤, 네 페르소나로 짧은 코칭을 덧붙여라.
- exec 가 실패하면(오류 출력) 저장 안 된 것이니, 지어내지 말고 "저장에 실패했다"고 알려라.

**리포트 (요청 시 exec):**
- 일일: `/home/ubuntu/pt_system/venv/bin/python /home/ubuntu/pt_system/reports/daily_report.py`
- 주간: `/home/ubuntu/pt_system/venv/bin/python /home/ubuntu/pt_system/reports/weekly_report.py`
  → 출력(집계 기반 리포트)을 그대로 사용자에게 전달한다.

**대시보드:** "대시보드/기록 보여줘" 요청엔 <http://mystatus-btr.duckdns.org/> 를 안내한다.

**사진:** 운동/식단 사진은
`/home/ubuntu/pt_system/venv/bin/python /home/ubuntu/pt_system/scripts/analyze_photo.py`
로 분석·저장한다(가장 최근 인바운드 이미지 자동 선택).

텔레그램은 더 이상 쓰지 않는다. 기록은 위 스크립트로만 저장한다.

## Related

- [Agent workspace](/concepts/agent-workspace)
