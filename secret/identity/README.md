# identity/ — 기기/게이트웨이 인증 정보

이 폴더는 OpenClaw 게이트웨이의 기기 인증 정보를 저장한다.
**서버 전용** — 로컬에는 실제 파일이 없다. git에도 올라가지 않는다.

## 서버 실제 파일 목록

| 파일 | 설명 |
|------|------|
| `device-auth.json` | 게이트웨이 인증 키 |
| `device.json` | 기기 ID 및 메타데이터 |

서버에서 경로: `~/.openclaw/secret/identity/`
