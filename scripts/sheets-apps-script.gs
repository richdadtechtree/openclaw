/**
 * 신문 브리핑 → 구글 시트 저장용 Apps Script 웹앱
 *
 * 설치:
 * 1) 구글 시트 새로 만들기 (예: "신문 브리핑 아카이브")
 * 2) 상단 메뉴 [확장 프로그램] → [Apps Script]
 * 3) 기본 코드 지우고 이 파일 전체를 붙여넣기
 * 4) 아래 SECRET 값을 아무 랜덤 문자열로 바꾸기 (서버 .env 의 SHEETS_WEBAPP_SECRET 과 동일하게)
 * 5) 우측 상단 [배포] → [새 배포] → 유형: "웹 앱"
 *      - 실행 계정: "나"
 *      - 액세스 권한: "모든 사용자"
 *    → 배포 → 권한 승인 → "웹 앱 URL"(.../exec) 복사
 * 6) 그 URL 을 서버 .env 의 SHEETS_WEBAPP_URL 에 넣기
 *
 * 코드를 수정하면 [배포] → [배포 관리] → 연필(수정) → "새 버전"으로 다시 배포해야 반영됩니다.
 */

const SECRET = 'CHANGE_ME_RANDOM';   // ← 서버 .env 의 SHEETS_WEBAPP_SECRET 과 똑같이 바꾸세요

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    if (SECRET && d.token !== SECRET) {
      return json_({ ok: false, error: 'unauthorized' });
    }
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
    // 헤더가 없으면 1회 추가
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(['일시', '날짜', '시간대', '제목', '본문']);
    }
    sheet.appendRow([
      new Date(),
      d.date || '',
      d.session || '',
      d.title || '',
      d.content || ''
    ]);
    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
