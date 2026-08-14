# secret/ — 서버 전용 비밀 파일 보관소

이 폴더는 **git에 올라가지 않는다** (`.gitignore`로 완전 제외).  
각 하위 폴더의 `README.md`만 구조 문서화 목적으로 추적된다.

---

## 폴더 구조 (서버 기준)

```
secret/
├── credentials/              # Slack/Telegram 계정 페어링 파일
│   ├── slack-default-allowFrom.json
│   ├── slack-pairing.json
│   ├── telegram-default-allowFrom.json
│   └── telegram-pairing.json
├── devices/                  # 페어링된 기기 정보
│   ├── paired.json
│   └── pending.json
├── identity/                 # 게이트웨이 기기 인증 정보
│   ├── device-auth.json
│   └── device.json
├── client_secret_176908463948-*.json   # Google OAuth 앱 시크릿
└── gateway.systemd.env       # systemd 서비스용 환경변수
```

---

## 파일별 관리 방법

| 파일/폴더 | 누가 생성 | 수동 관리 여부 |
|-----------|-----------|---------------|
| `credentials/` | OpenClaw 자동 생성 | ❌ 건드리지 말것 |
| `devices/` | OpenClaw 자동 생성 | ❌ 건드리지 말것 |
| `identity/` | OpenClaw 자동 생성 | ❌ 건드리지 말것 |
| `client_secret_*.json` | Google Console에서 다운로드 | ✅ 수동 |
| `gateway.systemd.env` | 초기 설정 시 수동 생성 | ✅ 수동 |

---

## 비밀 관리 전략 전체 구조

```
~/.openclaw/
├── .env                  ← 메인 비밀 보관소 (API 키, 토큰)
│                            openclaw가 자동으로 읽음 → 이동 불가
├── openclaw.json         ← 설정 파일 (토큰은 ${ENV_VAR} 참조)
│                            git에 올라감 ✅
└── secret/               ← 기타 민감 파일 (openclaw 내부 생성물)
    ├── credentials/         git에 올라가지 않음 ❌
    ├── devices/
    ├── identity/
    └── ...
```

---

## 서버 신규 설치 시 체크리스트

- [ ] `.env` 파일 생성 (`.env.example` 참고)
- [ ] `secret/client_secret_*.json` 복사 (Google OAuth 사용 시)
- [ ] `secret/gateway.systemd.env` 복사 (systemd 서비스 설정 시)
- [ ] `credentials/`, `devices/`, `identity/` 는 openclaw 첫 실행 시 자동 생성됨

---

## 절대 하지 말 것

- `git add secret/` 하지 마라 (README 제외)
- 토큰/키를 로그나 마크다운에 직접 적어 git push 하지 마라
- `.env` 를 `secret/` 으로 옮기지 마라 (openclaw가 못 읽음)
