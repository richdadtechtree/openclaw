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

## 구글 (Google Workspace) — `gog` CLI 로 접근  ⚠️ `gcalcli` 아님

구글 **캘린더 · Gmail · 시트 · 드라이브 · 문서 · 연락처**는 전부 **`gog`(gogcli)** 명령으로 쓴다.
`gcalcli` 는 설치돼 있지 않으니 찾지 말 것. `exec` 툴로 `gog ...` 를 실행하면 된다.

- 인증 계정: **`bbonoyo@gmail.com`** (기본, OAuth). 확인: `gog auth list`
- 스코프: calendar, gmail, drive, sheets, docs, contacts (모두 인증됨)
- keyring 암호는 게이트웨이 환경변수에 있어 별도 입력 없이 바로 동작한다.

검증된 명령 예시:
- 캘린더: `gog calendar list`
- Gmail:  `gog gmail search "is:unread"`   (읽기: `gog gmail --help`)
- 시트:   `gog sheets create "제목"` · `gog sheets get <시트ID> <범위>` · `gog sheets append <시트ID> <범위> <값...>`
- 드라이브: `gog drive --help` 로 하위 명령 확인
- **모르는 명령·플래그는 `gog <서비스> --help` 로 직접 확인**하고 쓴다.
- 스크립트/파싱이 필요하면 `-j`(JSON) 또는 `-p`(TSV). 안전: 메일 전송 막으려면 `--gmail-no-send`.

## Related

- [Agent workspace](/concepts/agent-workspace)
