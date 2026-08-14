# credentials/ — Slack/Telegram 계정 페어링 파일

이 폴더는 OpenClaw가 Slack/Telegram 계정을 인증하면서 자동 생성한다.
**서버 전용** — 로컬에는 실제 파일이 없다. git에도 올라가지 않는다.

## 서버 실제 파일 목록

| 파일 | 설명 |
|------|------|
| `slack-default-allowFrom.json` | Slack default 계정 허용 사용자 |
| `slack-pairing.json` | Slack 계정 페어링 토큰 |
| `telegram-default-allowFrom.json` | Telegram default 계정 허용 사용자 |
| `telegram-pairing.json` | Telegram 계정 페어링 토큰 |

이 파일들은 openclaw가 `credentials/` 경로에서 자동으로 읽는다.
서버에서 경로: `~/.openclaw/secret/credentials/`
