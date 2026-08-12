import json

with open("news_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# 데이터가 리스트인지 딕셔너리 안의 리스트인지 확인
articles = data if isinstance(data, list) else data.get("articles", [])

content = "# 오늘의 뉴스 브리핑 (2026년 8월 9일)\n\n"
content += "## 📰 주요 기사 요약\n\n"

for i, art in enumerate(articles, 1):
    if isinstance(art, str):
        content += f"### {i}. {art}\n\n"
        continue
    title = art.get('title', '제목 없음')
    source = art.get('source', '출처 미상')
    link = art.get('link', '#')
    summary = art.get('summary', '요약 없음')
    content += f"### {i}. {title}\n"
    content += f"- **언론사:** {source}\n"
    content += f"- **링크:** {link}\n"
    content += f"- **내용 요약:** {summary}\n\n"

content += """## 오늘의 판세

• 관통 테마
주식·부동산 시장의 불확실성 속에서 포트폴리오 다변화(바이오 등)와 제도 변화(부부 공동명의 종부세 등)에 대한 관심 고조.

• 숨은 연결
전통적 투자 방식의 한계를 극복하기 위해 신기술·성장 산업(바이오, 낸드 자회사 투자 유치) 및 자산 재배치 전략이 대두되고 있음.

• 이번 주 체크포인트
부부 공동명의 종부세 관련 세법 개정안 및 주요 대기업 투자 관련 공시 지표 확인.

• 포트폴리오 점검
단일 섹터 집중 투자(반도체 몰빵 등)를 지양하고 헬스케어/바이오 등 분산 투자 전략 점검.
"""

with open("briefing_sheet.md", "w", encoding="utf-8") as f:
    f.write(content)

print("briefing_sheet.md generated successfully.")
