#!/usr/bin/env python3
"""
debate.py — 다중 AI 토론 오케스트레이터 (OpenClaw #ai-토론 채널용)

계획서: openclaw_multi_model_debate_plan.md 를 그대로 구현한다.

사용 (openclaw debate 에이전트의 SOUL.md 가 exec 툴로 실행):
  python3 ~/.openclaw/scripts/debate.py "<슬랙 사용자 원문 메시지>"

모드 (원문 맨 앞 키워드로 결정):
  (키워드 없음)       → 개별 답변 모드 (기본값)
  "개별답변: <질문>"   → 개별 답변 모드
  "토론: <질문>"       → 토론 모드 (1차 의견 → 반론 1회 → 사회자 종합)
  "상태"               → 오늘 호출 현황 리포트
  "도움말"             → 사용법 안내

Gemini/Qwen/Mistral 3개는 openclaw 의 모델 라우팅을 거치지 않고 각 공급자
REST API 를 직접 호출한다 — 함수 호출/툴을 전혀 주지 않으므로
"명령 실행·파일쓰기·메시지 발송 도구 금지" 원칙이 자동으로 지켜진다.

GPT 만 예외로, ChatGPT Plus 구독(OAuth) 사용량을 그대로 쓰기 위해 별도 API 키 대신
**openclaw 게이트웨이의 OpenAI 호환 Chat Completions HTTP 엔드포인트**
(`gateway.http.endpoints.chatCompletions.enabled: true`)를 통해
전용 무툴(no-tool) 에이전트 `debate-gpt`(openclaw.json 에 등록, tools.profile="minimal"
+ deny exec)를 호출한다. 이 경로는 openclaw 가 "정상 에이전트 한 턴 실행"으로 처리하므로
완전히 격리되진 않지만, 전용 에이전트에 툴을 최대한 막아뒀다 — 운영 중 이상 동작(파일 접근
시도 등)이 보이면 즉시 확인 필요.

Slack 전송은 하지 않는다 — 이 스크립트의 stdout 을 그대로 openclaw 에이전트가
슬랙 스레드에 답장으로 올린다(에이전트 SOUL.md 지시).

필요 (.env, openclaw 루트):
  GATEWAY_TOKEN          게이트웨이 인증 토큰 (이미 있음 — openclaw.json gateway.auth.token 과 동일)
  GEMINI_API_KEY         이미 있음 (google-generative-ai 네이티브 API)
  OPENROUTER_API_KEY    Qwen(무료) 호출용
  MISTRAL_API_KEY       Mistral(무료) 호출용
  DEBATE_GEMINI_MODEL /
  DEBATE_QWEN_MODEL / DEBATE_QWEN_MODEL_FALLBACK /
  DEBATE_MISTRAL_MODEL / DEBATE_MISTRAL_MODEL_FALLBACK   (없으면 기본값 사용 — 반드시 구축 당일 확인)
  DEBATE_GATEWAY_URL     게이트웨이 chat completions 주소 (기본 http://127.0.0.1:18789/v1/chat/completions)
  DEBATE_GPT_AGENT       게이트웨이로 부를 openclaw 에이전트 (기본 openclaw/debate-gpt)
  DEBATE_RATE_LIMIT_PER_MIN   분당 최대 요청 수 (기본 3)
  DEBATE_TIMEOUT_SEC          모델별 호출 제한시간 초 (기본 25)
"""
import concurrent.futures
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

# ── 0. .env 로드 (slack_text.py 와 동일 패턴, 추가 의존성 없음) ─────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(BASE_DIR, "workspace", "debate", "state")
USAGE_LOG = os.path.join(STATE_DIR, "usage_log.jsonl")
RATE_FILE = os.path.join(STATE_DIR, "rate_limit.json")


def load_env():
    for path in (os.path.join(BASE_DIR, ".env"), ".env"):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            break


load_env()

# ── 1. 설정값 (계획서 §17 "구축 시 기록할 값") ──────────────────────────────
# ⚠️ 무료 모델 ID는 자주 바뀐다. 아래는 기본값(placeholder)이며,
#    구축 당일 OpenRouter/Mistral 콘솔에서 실제 사용 가능한 ID로 .env 의
#    DEBATE_QWEN_MODEL / DEBATE_MISTRAL_MODEL 등을 채워 넣어야 한다.
CONFIG = {
    "gateway_url": os.getenv("DEBATE_GATEWAY_URL", "http://127.0.0.1:18789/v1/chat/completions"),
    "gpt_agent": os.getenv("DEBATE_GPT_AGENT", "openclaw/debate-gpt"),
    "gemini_model": os.getenv("DEBATE_GEMINI_MODEL", "gemini-flash-latest"),
    "qwen_model": os.getenv("DEBATE_QWEN_MODEL", "qwen/qwen3-235b-a22b:free"),
    "qwen_model_fallback": os.getenv("DEBATE_QWEN_MODEL_FALLBACK", "qwen/qwen-2.5-72b-instruct:free"),
    "mistral_model": os.getenv("DEBATE_MISTRAL_MODEL", "mistral-small-latest"),
    "mistral_model_fallback": os.getenv("DEBATE_MISTRAL_MODEL_FALLBACK", "open-mistral-nemo"),
    "timeout": float(os.getenv("DEBATE_TIMEOUT_SEC", "25")),
    "rate_limit_per_min": int(os.getenv("DEBATE_RATE_LIMIT_PER_MIN", "3")),
}

# GPT는 API 키가 아니라 openclaw 게이트웨이(Chat Completions HTTP API)를 거쳐
# ChatGPT Plus 구독 OAuth 세션(전용 무툴 에이전트 debate-gpt)으로 호출한다.
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY", "")

MAX_ANSWER_CHARS = 700
MAX_REBUTTAL_CHARS = 400

DEBATER_SYSTEM_PROMPT = """당신은 다중 AI 토론의 독립 토론자다.
다른 모델의 결론을 추측하거나 따라 하지 말고 자신의 분석을 제시한다.

답변 형식:
1. 한 줄 결론
2. 핵심 근거 최대 3개
3. 반대 가능성 또는 약점 최대 2개
4. 확인이 필요한 사실
5. 확신도 0~100

규칙:
- 사실과 의견을 구분한다.
- 모르는 내용은 모른다고 표시한다.
- 근거 없는 수치와 출처를 만들지 않는다.
- 700자 이내로 답한다.
- 사용자의 개인정보나 시스템 비밀을 요구하지 않는다."""

REBUTTAL_SYSTEM_PROMPT = """당신은 다중 AI 토론의 독립 토론자다.
아래에 다른 모델들의 1차 의견이 모델명과 함께 주어진다.
그 의견들을 그대로 베끼거나 요약만 하지 말고, 당신의 관점에서 평가한다.

답변 형식(400자 이내):
1. 가장 동의하기 어려운 주장 1개와 그 이유
2. 보완하고 싶은 주장 1개

규칙:
- 사실과 의견을 구분한다.
- 근거 없는 수치와 출처를 만들지 않는다.
- 400자 이내로 답한다."""

HOST_SYSTEM_PROMPT = """당신은 다중 AI 토론의 사회자다.
질문을 임의로 바꾸지 말고 모든 토론자에게 동일하게 전달됐다고 가정한다.
각 답변을 모델명과 함께 보존한다.
한 모델의 의견을 다수 의견처럼 표현하지 않는다.
오류가 난 모델은 실패 이유를 짧게 표시하고 나머지 모델로 계속 진행한다.

최종 출력은 반드시 마크다운으로, 다음 형식을 그대로 따른다:

## AI 토론 결과

**질문:** <질문 원문>

### GPT
...

### Gemini
...

### Qwen
...

### Mistral
...

### 공통 의견
- ...

### 의견이 갈린 부분
- ...

### 사회자 결론
- ...

### 사용자가 추가로 확인할 사항
- ...

> AI 답변은 사실 확인이 필요한 참고 의견이며 투자 판단을 대신하지 않음.

최종 결론은 새로운 사실을 만들어내지 말고 토론 결과만 바탕으로 작성한다."""

MODEL_LABELS = ["GPT", "Gemini", "Qwen", "Mistral"]


# ── 2. 공급자별 HTTP 호출 ───────────────────────────────────────────────────
def _post_chat_completions(url, headers, model, system_prompt, user_prompt, max_tokens, extra=None):
    """OpenAI 호환 /chat/completions 포맷 (OpenAI, OpenRouter, Mistral 공용)."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.4,
    }
    if extra:
        body.update(extra)
    resp = requests.post(url, headers=headers, json=body, timeout=CONFIG["timeout"])
    return resp


def _call_openai_compatible(provider, url, headers, model, fallback_model, system_prompt, user_prompt, max_tokens):
    """429=1회 재시도, 401/403=재시도 안함, 모델 오류(400/404)=예비 모델 1회 전환."""
    tried_fallback = False
    cur_model = model
    for attempt in range(2):
        try:
            resp = _post_chat_completions(url, headers, cur_model, system_prompt, user_prompt, max_tokens)
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "응답 지연(타임아웃)", "model": cur_model}
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": f"연결 오류: {e}", "model": cur_model}

        if resp.status_code == 200:
            data = resp.json()
            try:
                text = data["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError):
                return {"ok": False, "error": "응답 파싱 실패", "model": cur_model}
            return {"ok": True, "text": text, "model": cur_model}

        if resp.status_code == 429:
            if attempt == 0:
                time.sleep(2)
                continue
            return {"ok": False, "error": "한도 초과(429)", "model": cur_model, "http_status": 429}

        if resp.status_code in (401, 403):
            return {"ok": False, "error": f"인증 오류({resp.status_code})", "model": cur_model, "http_status": resp.status_code}

        if resp.status_code in (400, 404) and fallback_model and not tried_fallback:
            tried_fallback = True
            cur_model = fallback_model
            continue

        return {"ok": False, "error": f"오류({resp.status_code}): {resp.text[:200]}", "model": cur_model, "http_status": resp.status_code}

    return {"ok": False, "error": "알 수 없는 오류", "model": cur_model}


def call_openai(system_prompt, user_prompt, max_tokens=900):
    """GPT는 openclaw 게이트웨이(Chat Completions HTTP API)를 거쳐 ChatGPT Plus 구독
    OAuth 세션으로 호출한다 — 별도 OPENAI_API_KEY/과금이 필요 없다.
    호출 대상은 전용 무툴 에이전트 openclaw.json 의 "debate-gpt"(tools.profile=minimal
    + exec deny)이며, 반드시 gateway.http.endpoints.chatCompletions.enabled=true 여야 한다."""
    if not GATEWAY_TOKEN:
        return {"ok": False, "error": "GATEWAY_TOKEN 미설정(게이트웨이 인증 토큰)", "model": CONFIG["gpt_agent"]}
    return _call_openai_compatible(
        "openai-gateway",
        CONFIG["gateway_url"],
        {"Authorization": f"Bearer {GATEWAY_TOKEN}", "Content-Type": "application/json"},
        CONFIG["gpt_agent"], None,
        system_prompt, user_prompt, max_tokens,
    )


def call_gemini(system_prompt, user_prompt, max_tokens=900):
    if not GEMINI_KEY:
        return {"ok": False, "error": "GEMINI_API_KEY 미설정", "model": CONFIG["gemini_model"]}
    model = CONFIG["gemini_model"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"}
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.4},
    }
    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=CONFIG["timeout"])
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "응답 지연(타임아웃)", "model": model}
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": f"연결 오류: {e}", "model": model}

        if resp.status_code == 200:
            data = resp.json()
            try:
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
            except (KeyError, IndexError):
                return {"ok": False, "error": "응답 파싱 실패", "model": model}
            if not text:
                return {"ok": False, "error": "빈 응답(안전 필터 가능)", "model": model}
            return {"ok": True, "text": text, "model": model}

        if resp.status_code == 429:
            if attempt == 0:
                time.sleep(2)
                continue
            return {"ok": False, "error": "한도 초과(429)", "model": model, "http_status": 429}

        if resp.status_code in (401, 403):
            return {"ok": False, "error": f"인증 오류({resp.status_code})", "model": model, "http_status": resp.status_code}

        return {"ok": False, "error": f"오류({resp.status_code}): {resp.text[:200]}", "model": model, "http_status": resp.status_code}

    return {"ok": False, "error": "알 수 없는 오류", "model": model}


def call_openrouter(system_prompt, user_prompt, max_tokens=900):
    if not OPENROUTER_KEY:
        return {"ok": False, "error": "OPENROUTER_API_KEY 미설정", "model": CONFIG["qwen_model"]}
    return _call_openai_compatible(
        "openrouter",
        "https://openrouter.ai/api/v1/chat/completions",
        {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://openclaw.ai",
            "X-Title": "OpenClaw AI Debate",
        },
        CONFIG["qwen_model"], CONFIG["qwen_model_fallback"],
        system_prompt, user_prompt, max_tokens,
    )


def call_mistral(system_prompt, user_prompt, max_tokens=900):
    if not MISTRAL_KEY:
        return {"ok": False, "error": "MISTRAL_API_KEY 미설정", "model": CONFIG["mistral_model"]}
    return _call_openai_compatible(
        "mistral",
        "https://api.mistral.ai/v1/chat/completions",
        {"Authorization": f"Bearer {MISTRAL_KEY}", "Content-Type": "application/json"},
        CONFIG["mistral_model"], CONFIG["mistral_model_fallback"],
        system_prompt, user_prompt, max_tokens,
    )


CALLERS = {
    "GPT": call_openai,
    "Gemini": call_gemini,
    "Qwen": call_openrouter,
    "Mistral": call_mistral,
}


def call_all_parallel(system_prompt, prompt_by_label, max_tokens):
    """4개 모델을 병렬로 호출한다. prompt_by_label 이 dict 면 모델별 다른 프롬프트,
    문자열이면 전 모델 동일 프롬프트."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {}
        for label, fn in CALLERS.items():
            user_prompt = prompt_by_label[label] if isinstance(prompt_by_label, dict) else prompt_by_label
            futures[ex.submit(fn, system_prompt, user_prompt, max_tokens)] = label
        for fut in concurrent.futures.as_completed(futures):
            label = futures[fut]
            try:
                results[label] = fut.result()
            except Exception as e:  # noqa: BLE001 — 개별 모델 실패가 전체를 죽이면 안 됨
                results[label] = {"ok": False, "error": f"내부 오류: {e}"}
    # 라벨 순서 고정(GPT/Gemini/Qwen/Mistral)
    return {label: results[label] for label in MODEL_LABELS}


def truncate(text, limit):
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…(길이 제한으로 생략)"


# ── 3. 사용량 로그 / 분당 레이트리밋 ─────────────────────────────────────────
def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def check_rate_limit():
    ensure_state_dir()
    now = time.time()
    window = now - 60
    timestamps = []
    if os.path.isfile(RATE_FILE):
        try:
            with open(RATE_FILE, encoding="utf-8") as f:
                timestamps = [t for t in json.load(f) if t > window]
        except (json.JSONDecodeError, OSError):
            timestamps = []
    if len(timestamps) >= CONFIG["rate_limit_per_min"]:
        return False
    timestamps.append(now)
    with open(RATE_FILE, "w", encoding="utf-8") as f:
        json.dump(timestamps, f)
    return True


def log_usage(mode, question, results):
    ensure_state_dir()
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "question_len": len(question),
        "results": {
            label: {
                "ok": r.get("ok"),
                "error": r.get("error"),
                "http_status": r.get("http_status"),
            }
            for label, r in results.items()
        },
    }
    with open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def status_report():
    ensure_state_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    total = today_calls = fail_429 = 0
    last_ts = None
    if os.path.isfile(USAGE_LOG):
        with open(USAGE_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                last_ts = e.get("ts", last_ts)
                if str(e.get("ts", "")).startswith(today):
                    today_calls += 1
                    for r in e.get("results", {}).values():
                        if r.get("http_status") == 429:
                            fail_429 += 1

    lines = [
        "## AI 토론 상태",
        "",
        f"- 오늘 호출 횟수: {today_calls}회 (누적 {total}회)",
        f"- 오늘 한도초과(429) 횟수: {fail_429}회",
        f"- 마지막 호출 시각(UTC): {last_ts or '기록 없음'}",
        "",
        "**등록된 모델 ID**",
        f"- GPT: 게이트웨이 경유 `{CONFIG['gpt_agent']}` (Plus OAuth, GATEWAY_TOKEN: {'설정됨' if GATEWAY_TOKEN else '❌ 없음'})",
        f"- Gemini: `{CONFIG['gemini_model']}` (키: {'설정됨' if GEMINI_KEY else '❌ 없음'})",
        f"- Qwen: `{CONFIG['qwen_model']}` / 예비 `{CONFIG['qwen_model_fallback']}` (키: {'설정됨' if OPENROUTER_KEY else '❌ 없음'})",
        f"- Mistral: `{CONFIG['mistral_model']}` / 예비 `{CONFIG['mistral_model_fallback']}` (키: {'설정됨' if MISTRAL_KEY else '❌ 없음'})",
        "",
        f"- 분당 호출 제한: {CONFIG['rate_limit_per_min']}회 / 모델 타임아웃: {CONFIG['timeout']}초",
    ]
    return "\n".join(lines)


def help_text():
    return (
        "## AI 토론 도움말\n\n"
        "```\n"
        "@AI토론 미국채는 정말 안전자산인가?\n"
        "@AI토론 개별답변: 서울 집값 상승 요인과 하락 요인을 분석해줘.\n"
        "@AI토론 토론: 지금 금을 추가 매수하는 것이 합리적인가?\n"
        "@AI토론 상태\n"
        "@AI토론 도움말\n"
        "```\n\n"
        "- 아무 키워드 없이 질문하면 **개별 답변 모드**(모델별 의견 + 사회자 종합)로 처리됩니다.\n"
        "- `토론:` 을 붙이면 1차 의견 → 모델 간 반론(1회) → 사회자 종합까지 진행됩니다(느리고 호출이 더 많음).\n"
        "- GPT/Gemini/Qwen/Mistral 4개 모델 중 일부가 실패해도 나머지 결과 + 사회자 요약은 표시됩니다.\n"
        "- AI 답변은 참고용이며 투자 판단을 대신하지 않습니다."
    )


# ── 4. 개별 답변 / 토론 모드 ─────────────────────────────────────────────────
def format_model_section(label, result):
    if result.get("ok"):
        return f"### {label}\n{truncate(result['text'], MAX_ANSWER_CHARS)}"
    return f"### {label}\n❌ 실패: {result.get('error', '알 수 없는 오류')}"


def fallback_raw_output(question, mode_label, round1, rebuttals=None, host_error=None):
    """사회자(GPT) 호출 자체가 실패했을 때 — 원문 답변만이라도 게시(계획서 §8)."""
    parts = [
        "## AI 토론 결과 (⚠️ 사회자 종합 실패 — 모델 원문만 표시)",
        "",
        f"**질문:** {question}",
        f"**모드:** {mode_label}",
    ]
    if host_error:
        parts.append(f"**사회자 오류:** {host_error}")
    parts.append("")
    for label in MODEL_LABELS:
        parts.append(format_model_section(label, round1[label]))
        parts.append("")
    if rebuttals:
        parts.append("### 반론 라운드")
        for label in MODEL_LABELS:
            r = rebuttals.get(label)
            if r is None:
                continue
            if r.get("ok"):
                parts.append(f"**{label} 반론:** {truncate(r['text'], MAX_REBUTTAL_CHARS)}")
            else:
                parts.append(f"**{label} 반론:** ❌ 실패: {r.get('error')}")
        parts.append("")
    parts.append("> AI 답변은 사실 확인이 필요한 참고 의견이며 투자 판단을 대신하지 않음.")
    return "\n".join(parts)


def run_individual(question):
    round1 = call_all_parallel(DEBATER_SYSTEM_PROMPT, question, max_tokens=900)

    ok_count = sum(1 for r in round1.values() if r.get("ok"))
    if ok_count == 0:
        log_usage("개별답변", question, round1)
        return (
            "## AI 토론 결과 — 전체 실패\n\n"
            f"**질문:** {question}\n\n"
            "GPT/Gemini/Qwen/Mistral 4개 모델 호출이 모두 실패했습니다.\n\n"
            + "\n".join(f"- {label}: {round1[label].get('error')}" for label in MODEL_LABELS)
            + "\n\n다시 시도하려면 잠시 후 같은 질문을 다시 보내주세요. "
              "반복 실패 시 `@AI토론 상태` 로 원인을 확인하세요."
        )

    host_prompt = build_host_prompt_individual(question, round1)
    host = call_openai(HOST_SYSTEM_PROMPT, host_prompt, max_tokens=1400)

    log_usage("개별답변", question, {**round1, "사회자": host})

    if host.get("ok"):
        return host["text"]
    return fallback_raw_output(question, "개별 답변", round1, host_error=host.get("error"))


def build_host_prompt_individual(question, round1):
    lines = [f"질문: {question}", "", "각 모델의 1차 의견(모델명과 함께 그대로 보존):", ""]
    for label in MODEL_LABELS:
        r = round1[label]
        if r.get("ok"):
            lines.append(f"[{label}]\n{r['text']}\n")
        else:
            lines.append(f"[{label}] (실패: {r.get('error')})\n")
    lines.append(
        "위 내용을 바탕으로 시스템 프롬프트에서 지정한 마크다운 형식(모델별 절 + 공통 의견 + "
        "의견이 갈린 부분 + 사회자 결론 + 확인할 사항)으로 정리하라. 실패한 모델은 실패 사실만 짧게 언급한다."
    )
    return "\n".join(lines)


def run_debate(question):
    round1 = call_all_parallel(DEBATER_SYSTEM_PROMPT, question, max_tokens=900)
    ok_labels = [label for label in MODEL_LABELS if round1[label].get("ok")]

    if not ok_labels:
        log_usage("토론", question, round1)
        return (
            "## AI 토론 결과 — 전체 실패\n\n"
            f"**질문:** {question}\n\n"
            "1차 의견 단계에서 4개 모델 호출이 모두 실패했습니다.\n\n"
            + "\n".join(f"- {label}: {round1[label].get('error')}" for label in MODEL_LABELS)
            + "\n\n다시 시도하려면 잠시 후 같은 질문을 다시 보내주세요."
        )

    # 반론 라운드: 성공한 모델에게만, "다른 모델들의 1차 의견"을 그대로 전달한다.
    # (계획서상 사회자의 "핵심 주장 정리"는 별도 LLM 호출 없이 기계적으로 조합해
    #  비용 예산 — 토론자8회+사회자1회=9회 — 을 지킨다.)
    rebuttal_prompts = {}
    for label in ok_labels:
        others = [
            f"[{other}] {round1[other]['text']}"
            for other in MODEL_LABELS
            if other != label and round1[other].get("ok")
        ]
        rebuttal_prompts[label] = (
            f"원래 질문: {question}\n\n다른 모델들의 1차 의견:\n" + "\n\n".join(others)
        )

    rebuttals = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(CALLERS[label], REBUTTAL_SYSTEM_PROMPT, rebuttal_prompts[label], 500): label
            for label in ok_labels
        }
        for fut in concurrent.futures.as_completed(futures):
            label = futures[fut]
            try:
                rebuttals[label] = fut.result()
            except Exception as e:  # noqa: BLE001
                rebuttals[label] = {"ok": False, "error": f"내부 오류: {e}"}

    host_prompt = build_host_prompt_debate(question, round1, rebuttals)
    host = call_openai(HOST_SYSTEM_PROMPT, host_prompt, max_tokens=1600)

    log_usage("토론", question, {**round1, **{f"{k}_반론": v for k, v in rebuttals.items()}, "사회자": host})

    if host.get("ok"):
        return host["text"]
    return fallback_raw_output(question, "토론", round1, rebuttals, host_error=host.get("error"))


def build_host_prompt_debate(question, round1, rebuttals):
    lines = [f"질문: {question}", "", "== 1차 의견 =="]
    for label in MODEL_LABELS:
        r = round1[label]
        lines.append(f"[{label}] " + (r["text"] if r.get("ok") else f"(실패: {r.get('error')})"))
    lines.append("\n== 반론 라운드(가장 동의하기 어려운 주장 + 보완 주장) ==")
    for label in MODEL_LABELS:
        r = rebuttals.get(label)
        if r is None:
            lines.append(f"[{label}] (1차 실패로 반론 라운드 제외)")
        elif r.get("ok"):
            lines.append(f"[{label}] {r['text']}")
        else:
            lines.append(f"[{label}] (반론 실패: {r.get('error')})")
    lines.append(
        "\n위 1차 의견과 반론을 바탕으로 시스템 프롬프트 형식대로 정리하라. "
        "합의점, 쟁점, 중요한 반론/소수의견, 사회자 최종 판단, 확인할 사항을 포함한다."
    )
    return "\n".join(lines)


# ── 5. 입력 파싱 & 엔트리포인트 ──────────────────────────────────────────────
def parse_input(raw):
    text = raw.strip()
    text = re.sub(r"^<@[A-Z0-9]+>\s*", "", text)  # 슬랙 멘션 잔여물 방어적으로 제거
    text = text.strip()

    if text in ("상태",):
        return "status", ""
    if text in ("도움말", "help", "Help"):
        return "help", ""

    m = re.match(r"^(개별답변|토론)\s*[:：]\s*(.+)$", text, re.DOTALL)
    if m:
        mode = "individual" if m.group(1) == "개별답변" else "debate"
        return mode, m.group(2).strip()

    return "individual", text


def main():
    if len(sys.argv) < 2:
        print("usage: python3 debate.py \"<질문 또는 명령>\"")
        sys.exit(1)

    raw = " ".join(sys.argv[1:])
    mode, question = parse_input(raw)

    if mode == "status":
        print(status_report())
        return
    if mode == "help":
        print(help_text())
        return

    if not question:
        print(help_text())
        return

    if not check_rate_limit():
        print(
            f"⏳ 요청이 너무 잦습니다. 분당 최대 {CONFIG['rate_limit_per_min']}회로 제한되어 있습니다. "
            "잠시 후 다시 시도해주세요."
        )
        return

    if mode == "debate":
        print(run_debate(question))
    else:
        print(run_individual(question))


if __name__ == "__main__":
    main()
