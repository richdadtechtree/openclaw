# Duck PT (Kim Jong-kook) Project Spec

## 1. 개요
Duck PT는 사용자의 건강 관리, 운동 루틴 설계, 식단 가이드, 그리고 바이탈 추적을 수행하는 AI 코칭 시스템입니다. 
코치는 '김종국' 캐릭터로서 단호하고 과학적이며 실질적인 피드백을 제공합니다.

## 2. 핵심 아키텍처
- **프론트엔드/대시보드**: Flask 백엔드 및 Vanilla CSS/JS 기반 웹 대시보드 (`mystatus-btr.duckdns.org`)
- **데이터베이스**: SQLite (`~/pt_data/pt.db`)
- **인터페이스**: Slack 챗봇 연동 & 웹 직접 모달 등록/수정/삭제
- **엔진**:
  - `WorkoutEngine.md`: 근력 & 유산소 운동 설계 및 부상 예방
  - `NutritionEngine.md`: 칼로리 및 단백질 섭취량 계산
  - `DecisionEngine.md`: 종합 코칭 의사결정 알고리즘

## 3. 기록 및 동기화 규칙
- Slack 메시지 및 웹 대시보드 입력 데이터는 파서(`save_message.py`)를 거쳐 즉시 SQLite DB에 기록됩니다.
- DB에 저장이 완료되면 웹 대시보드 및 일간/주간 브리핑에 실시간 연동됩니다.
