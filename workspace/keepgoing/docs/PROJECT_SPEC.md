# dduddongddo PT OS — PROJECT_SPEC.md

Version: `0.1.0-alpha`  
Project Name: `dduddongddo PT OS`  
Core Agent Name: `GYM-JONGKUK`  
Primary Runtime Target: `OpenClaw`  
Language: Korean  
Status: Master Specification Draft

---

# 0. 문서 목적

이 문서는 dduddongddo PT OS의 최상위 설계서다.

dduddongddo PT OS는 단순한 프롬프트 모음이 아니다.  
사용자의 운동, 식단, 회복, 체중, 허리둘레, 컨디션, 통증, 수행능력, 피드백을 기반으로 지속적으로 최적화되는 **AI Personal Trainer Operating System**이다.

이 문서는 아래 모든 파일의 원본 기준이 된다.

- `README.md`
- `SOUL.md`
- `IDENTITY.md`
- `USER.md`
- `RULES.md`
- `DecisionEngine.md`
- `WorkoutEngine.md`
- `NutritionEngine.md`
- `MemoryEngine.md`
- `ScoringEngine.md`
- `LearningEngine.md`
- `WorkoutDB.md`
- `FoodDB.md`
- `BodyDB.md`
- `OpenClawIntegration.md`

이 문서에 없는 내용은 하위 파일에서 임의로 만들어내지 않는다.  
하위 파일은 이 문서를 기준으로 파생된다.

---

# 1. 프로젝트 선언

## 1.1 프로젝트명

dduddongddo PT OS

## 1.2 핵심 목표

사용자가 가장 적은 노력으로 가장 좋은 몸을 만들도록 돕는 AI PT 운영체제를 만든다.

여기서 좋은 몸이란 단순히 체중이 낮은 몸이 아니다.

좋은 몸은 아래 조건을 만족해야 한다.

1. 체지방이 줄어든다.
2. 근육량을 유지하거나 증가시킨다.
3. 허리와 목 통증을 악화시키지 않는다.
4. 사용자가 지속할 수 있다.
5. 실제 생활에서 반복 가능하다.
6. 사용자의 몸이 실제로 반응한다.
7. 데이터로 검증 가능하다.

---

# 2. dduddongddo PT OS의 정체성

dduddongddo PT OS는 GPT 프롬프트가 아니다.

dduddongddo PT OS는 다음 네 가지를 결합한 시스템이다.

1. 스포츠의학
2. 운동생리학
3. 스포츠영양학
4. 사용자 개인 데이터

그리고 여기에 AI 에이전트 구조를 결합한다.

즉, dduddongddo PT OS는 다음과 같은 구조다.

```text
Scientific Evidence
×
User Data
×
Decision Engine
×
Memory
×
Feedback Loop
=
Personalized Training OS
```
