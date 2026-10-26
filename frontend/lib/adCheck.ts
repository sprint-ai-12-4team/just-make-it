// 표시광고법·식품표시광고법에서 근거 없이 쓰면 문제가 되기 쉬운 말. 막지 않고 알려만 줌
// ponytail: 단순 포함 검사라 "최고급"처럼 괜찮은 말도 잡음. 오탐이 많으면 단어 경계 규칙 추가
const RISKY = ["최고", "최상", "최초", "최저가", "1위", "1등", "넘버원", "No.1", "100%", "유일", "완벽", "무조건", "보장", "특효", "완치", "치료", "예방", "효능", "부작용"];

/** 문구에 들어 있는 조심할 말 (목록 순서, 중복 없음) */
export function riskyWords(text: string): string[] {
  const t = text.toLowerCase();
  return RISKY.filter((w) => t.includes(w.toLowerCase()));
}
