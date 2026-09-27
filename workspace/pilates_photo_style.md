<!--
  마이비필라테스 사진 — 이미지 생성 공통 조건 (2026-09-27 신설)

  이 파일은 scripts/pilates_blog.py 가 읽어서 배달 메시지 맨 아래에 붙입니다.
  각 사진의 `프롬프트:` 줄은 **장면 설명만** 담고, 아래 A·B 를 앞뒤에 붙여 쓰면
  완성된 이미지 생성 프롬프트가 됩니다.

      [A] + [그 사진의 프롬프트 줄] + [B]

  왜 이렇게 나눴나
  ---------------
  한 프롬프트에 화살표·근육 해부도·형광 효과·큰 한글 문구를 같이 넣으면
  모델이 "실제 사진"이 아니라 "합성 광고물"로 해석합니다. 그래서
    · 사진은 글자·그래픽 없이 **순수 사진**으로만 생성하고
    · 캡션·화살표·근육 표시는 **디자인 단계에서 따로 얹습니다.**

  고쳐 쓸 때
  ----------
  · 인물이 다른 사진(남성·산모 등)은 프롬프트 줄 맨 앞에 인물 설명이 따로 적혀 있습니다.
    그때는 A 의 인물 문장을 그 설명으로 바꿔 쓰세요.
  · 인물이 없는 사물 컷(플랫레이·물병 등)은 A 의 인물 문장을 빼고 쓰세요.
  · 이 파일을 고치면 다음 배달부터 바로 반영됩니다.
-->

## A. 앞에 붙일 것 (사진의 성격 + 인물 + 피부)

A candid editorial fitness photograph, taken during an actual training session at a real Pilates studio in Seoul. Subject: an adult East Asian woman in her late 20s, dark hair loosely tied back, minimal makeup, skin slightly flushed from exercise, fine skin texture with visible pores and soft facial down, natural creases at the joints, plain fitted training clothes.

## B. 뒤에 붙일 것 (카메라 + 조명 + 배경 + 네거티브)

Camera about 3-4 meters away at roughly hip height, 70mm equivalent lens, kept parallel to the frontal plane of the body; natural leg and torso proportions, no wide-angle foreshortening. Soft directional daylight from one large window on the left, every shadow falling the same way, shallow depth of field with the background gently out of focus. Background kept sparse, only two or three meaningful objects of a real studio. Realistic muscular effort: subtle tension in the working muscles, slight fabric compression, weight visibly distributed through both feet. Negative prompt: no text, no lettering, no Korean characters, no arrows, no anatomical or muscle overlays, no glowing or heat effects, no checkboxes, no infographic or poster layout, no advertisement look, no beauty retouching, no plastic or glossy skin, no unnatural symmetry, no extra limbs.

## C. 꼭 지킬 것

- 사진 안에 **글자를 넣지 않습니다.** 캡션은 사진 위에 디자인 단계에서 얹습니다.
- 화살표·근육 해부도·형광 발광·체크박스는 사진 생성에 넣지 않습니다. 필요하면 후편집으로 얹습니다.
- `promotional poster`, `tutorial infographic`, `polished advertisement` 같은 표현은 쓰지 않습니다.
- `perfect form` 대신 실제로 버티는 순간을 묘사합니다.
- 광각(24~35mm)·낮은 카메라 위치는 다리가 짧고 굵게 나오므로 피합니다.
