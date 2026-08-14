# openclaw 설정 자동 동기화 (git push / pull)

설정·콘텐츠(에이전트 SOUL, 프롬프트, `cron/jobs.json` 등)를 수정하면 자동으로
git 에 push 하고, **서버가 주기적으로 pull** 해서 반영하도록 하는 구성입니다.

```
 [클로드/로컬에서 수정]                         [서버 (openclaw 실행 중)]
        │                                              │
        │  scripts/git-auto-push.sh                    │  cron 매 1분
        ▼                                              ▼
   git commit + push  ──────►  GitHub  ◄──────  git-auto-pull.sh
                                                    │ 설정만 동기화 (런타임 보존)
                                                    ▼
                                             systemctl restart openclaw
```

## 무엇이 git 으로 관리되나

| 대상 | git 추적 | 설명 |
|------|----------|------|
| `openclaw.json` | ✅ 추적 | 토큰은 `${ENV_VAR}` 참조로 분리됨 |
| `cron/jobs.json` | ✅ 추적 | 스케줄 설정 |
| `workspace/**/*.md` | ✅ 추적 | SOUL.md, IDENTITY.md 등 캐릭터 설정 |
| `agents/**/*.md` | ✅ 추적 | 에이전트 설정 마크다운 |
| `scripts/` | ✅ 추적 | 유틸 스크립트 |
| `.env.example` | ✅ 추적 | 빈 양식 (실제 값 없음) |
| `.env` | ❌ 제외 | **실제 비밀값** — 서버 로컬 전용 |
| `secret/` | ❌ 제외 | **서버 수동 관리** — credentials, identity 등 |
| `agents/*/sessions/` | ❌ 제외 | 세션 기록 — 런타임 생성물 |
| `*.sqlite*` | ❌ 제외 | OpenClaw 내부 DB |
| `*.bak*`, `*.migrated` | ❌ 제외 | 백업/스냅샷 |
| `logs/`, `slack_logs/` | ❌ 제외 | 로그 |



런타임 파일을 추적에서 제외했기 때문에 서버 pull 이 항상 깔끔하게 동작하고,
서버가 만든 세션·로그가 pull 때문에 삭제되지 않습니다.

## 1. Push (수정하는 쪽 — 클로드/로컬)

파일을 수정한 뒤 실행:

```bash
scripts/git-auto-push.sh                # 자동 커밋 메시지
scripts/git-auto-push.sh "jobs 수정"    # 메시지 직접 지정
```

- 변경이 없으면 아무것도 하지 않습니다.
- 푸시 실패 시 지수 백오프(2·4·8·16초)로 재시도합니다.
- 기본은 **현재 체크아웃된 브랜치**로 푸시합니다.
  다른 브랜치로 고정하려면 `OPENCLAW_GIT_BRANCH=main scripts/git-auto-push.sh`.

## 2. Pull (서버) — 최초 1회 설정

서버의 리포 디렉토리(예: `/home/ubuntu/.openclaw`)에서:

```bash
# 브랜치·재시작 명령을 환경에 맞게 지정해서 cron 등록
OPENCLAW_GIT_BRANCH=main \
OPENCLAW_RESTART_CMD="sudo systemctl restart openclaw" \
scripts/setup-server-cron.sh
```

이렇게 하면 `git-auto-pull.sh` 가 **매 1분**마다 실행되어,
원격에 새 커밋이 있을 때만 설정을 반영하고 서비스를 재시작합니다.
(새 커밋이 없으면 재시작하지 않습니다.)

### 서비스 이름 / 재시작 방식

- 실제 서비스명: **`openclaw-gateway.service`** (systemd user 서비스)
- 재시작: `systemctl --user restart openclaw-gateway.service`
- 상태: `systemctl --user status openclaw-gateway.service`
- 로그: `journalctl --user -u openclaw-gateway.service -f`

`sudo` 로 재시작한다면 cron 이 비밀번호 없이 실행되도록 sudoers 설정이 필요합니다
(`setup-server-cron.sh` 실행 시 안내 문구 출력). 예:

```
# /etc/sudoers.d/openclaw  (visudo 로 편집)
ubuntu ALL=(root) NOPASSWD: /bin/systemctl restart openclaw
```

### 수동으로 한 번 돌려보기 / 로그

```bash
OPENCLAW_GIT_BRANCH=main scripts/git-auto-pull.sh   # 즉시 1회 실행
tail -f scripts/auto-pull.log                        # cron 로그 확인
crontab -l                                            # 등록 확인
```

## 동작 원리 (안전성)

서버 pull 은 `git pull` 대신 다음을 사용합니다:

```
git fetch origin <branch>
git reset --mixed <remote>     # HEAD·index 만 원격에 맞춤 (working tree 유지)
git checkout --force -- .      # 추적 파일(설정)만 원격 상태로 갱신
```

- 추적 대상은 설정 파일뿐 → 강제 갱신해도 **런타임 데이터 손실 없음**.
- untracked(런타임) 파일은 위 명령이 절대 건드리지 않음 → **디스크에 그대로 보존**.
- `flock` 으로 중복 실행 방지.

## ⚠️ 보안 참고 — 토큰 노출

이전에 `openclaw.json.bak*`, `*.last-good` 등 **백업 파일이 git 에 커밋**되어 있었고,
그 안에 텔레그램 봇 토큰·API 키가 포함되어 있었습니다. 이번 변경으로 앞으로는
추적에서 제외되지만, **git 히스토리에는 남아 있습니다.**

권장:
1. 노출된 토큰/키를 **재발급(rotate)** 하세요 (텔레그램 봇 토큰, Brave API 키 등).
2. 필요하면 히스토리에서 제거(`git filter-repo` 등)하세요. 히스토리 재작성은
   협업/원격에 영향을 주므로 별도로 진행하는 것을 권장합니다.
