// 대기 중 정보 카드 (service_consulting.md C). 서버 GET /tips가 없을 때 쓰는 기본 카드
// ponytail: 직접 쓴 고정 목록. 서버 카드(공식 API 배치)가 생기면 이건 대체용으로만 남김
// 플랫폼·법 카드는 단정하지 않고 "도움말을 확인하세요"로 끝냄 — 정책이 자주 바뀜
import type { Purpose, Tip } from "./types";

type Local = Tip & { purposes?: Purpose[]; date?: string /* MM-DD, 시즌만 */ };

export const TIPS: Local[] = [
  // 시즌: 그날 21일 전부터 보임
  { id: "season-0214", kind: "season", date: "02-14", title: "2월 14일 밸런타인데이", body: "초콜릿·디저트·꽃 가게라면 일주일 전부터 올려 두세요." },
  { id: "season-0314", kind: "season", date: "03-14", title: "3월 14일 화이트데이", body: "사탕·선물 세트 광고는 10일 전쯤 올리면 미리 고르는 손님이 봐요." },
  { id: "season-0505", kind: "season", date: "05-05", title: "5월 5일 어린이날", body: "가족 손님이 많은 가게라면 '가족 세트'처럼 묶어서 알려 보세요." },
  { id: "season-0508", kind: "season", date: "05-08", title: "5월 8일 어버이날", body: "꽃·케이크·선물 가게는 예약을 미리 받는다고 함께 알리면 좋아요." },
  { id: "season-0515", kind: "season", date: "05-15", title: "5월 15일 스승의 날", body: "작은 선물·꽃 광고는 학부모가 보는 동네 채널에 올려 보세요." },
  { id: "season-1111", kind: "season", date: "11-11", title: "11월 11일 빼빼로데이", body: "과자·디저트 가게라면 일주일 전부터 '한정' 문구로 알려 보세요." },
  { id: "season-1225", kind: "season", date: "12-25", title: "12월 25일 크리스마스", body: "케이크·선물 예약은 2주 전부터 받는 가게가 많아요. 예약 마감일을 같이 적어 보세요." },
  { id: "season-1231", kind: "season", date: "12-31", title: "한 해 마무리", body: "'올해 감사했어요' 단골 인사 광고는 할인이 없어도 반응이 좋아요." },

  // 후가공 요령: 결과 화면 기능으로 바로 이어짐
  { id: "howto-cutout", kind: "howto", title: "상품만 남기고 배경 색 바꾸기", body: "결과가 나오면 '배경 지우고 색 채우기'를 눌러 보세요. 흰 배경은 쇼핑몰에 잘 어울려요." },
  { id: "howto-text", kind: "howto", title: "글자가 상품을 가린다면", body: "'글자 직접 고치기'에서 글자를 끌어 옮기거나 크기를 줄일 수 있어요." },
  { id: "howto-remake", kind: "howto", title: "마음에 안 들면 칩 하나만", body: "'더 밝게', '배경 단순하게'를 골라 다시 만들면 처음보다 빨리 원하는 그림에 가까워져요." },
  { id: "howto-qr", kind: "howto", title: "그림에 가게 QR 넣기", body: "결과 화면에서 가게 링크를 넣으면 QR을 그림 구석에 붙여 드려요. 전단지에 특히 좋아요." },
  { id: "howto-copy", kind: "howto", title: "같은 문구로 해시태그까지", body: "결과 화면의 '다른 곳에 올릴 글로 바꾸기'에서 해시태그·블로그 제목을 바로 받아 보세요." },

  // 플랫폼별
  { id: "platform-ig-ratio", kind: "platform", purposes: ["instagram"], title: "인스타 피드는 세로가 더 크게 보여요", body: "정사각형도 괜찮지만, 세로형(4:5)이 화면을 더 많이 차지해요. 올리기 전에 미리보기로 잘리는 곳을 확인하세요." },
  { id: "platform-ig-grid", kind: "platform", purposes: ["instagram"], title: "프로필 격자에서는 양옆이 잘려요", body: "결과 화면의 '올리면 가려지는 곳 보기'로 중요한 글자가 잘리지 않는지 확인하세요." },
  { id: "platform-store-main", kind: "platform", purposes: ["commerce"], title: "쇼핑몰 대표 이미지는 글자 없이", body: "대표 이미지에 글자·워터마크를 넣으면 검색에 덜 나올 수 있어요. 올리기 전에 판매자 도움말을 확인하세요." },
  { id: "platform-store-white", kind: "platform", purposes: ["commerce"], title: "대표 이미지는 깔끔한 배경이 유리해요", body: "흰 배경을 권하는 쇼핑몰이 많아요. '배경 지우고 색 채우기'에서 흰색을 골라 보세요." },
  { id: "platform-yt-size", kind: "platform", purposes: ["youtube"], title: "유튜브 썸네일은 2MB까지", body: "파일이 크면 올라가지 않아요. 저장한 그림이 크다면 JPG로 바꿔 올려 보세요." },
  { id: "platform-yt-time", kind: "platform", purposes: ["youtube"], title: "오른쪽 아래는 영상 길이에 가려요", body: "중요한 글자는 가운데나 왼쪽에 두세요." },
  { id: "platform-kakao-ad", kind: "platform", purposes: ["kakao"], title: "광고 메시지는 맨 앞에 (광고)", body: "카톡·문자로 광고를 보낼 때는 '(광고)' 표시와 수신 거부 방법을 넣어야 해요. 밤 9시~아침 8시에는 따로 동의가 필요해요." },

  // 법 (모든 곳 공통)
  { id: "law-best", kind: "law", title: "'최고·1위'에는 근거가 필요해요", body: "근거(출처·기준일) 없이 쓰면 표시광고법에 걸릴 수 있어요." },
  { id: "law-food", kind: "law", title: "음식에 '병에 좋다'는 말은 조심", body: "일반 식품에 질병 예방·치료 효과를 적으면 안 돼요." },
  { id: "law-discount", kind: "law", title: "할인 전 가격은 실제로 팔던 가격", body: "올린 적 없는 가격에서 깎아 주는 것처럼 보이면 문제가 될 수 있어요." },
  { id: "law-face", kind: "law", title: "손님 얼굴·남의 로고는 빼 주세요", body: "허락 없이 쓰면 초상권·상표권 문제가 생길 수 있어요." },
];

const DAY = 86_400_000;

/** 오늘부터 그날까지 남은 날 (올해 지났으면 내년) */
export function daysUntil(mmdd: string, today: Date): number {
  const [m, d] = mmdd.split("-").map(Number);
  const base = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  let t = Date.UTC(today.getFullYear(), m - 1, d);
  if (t < base) t = Date.UTC(today.getFullYear() + 1, m - 1, d);
  return Math.round((t - base) / DAY);
}

/** 보여 줄 카드: 다가오는 시즌 → 이 목적 플랫폼 → 요령·법 섞어서 */
export function pickTips(purpose: Purpose | undefined, today: Date, limit = 6): Tip[] {
  const season = TIPS.filter((t) => t.date && daysUntil(t.date, today) <= 21).sort((a, b) => daysUntil(a.date!, today) - daysUntil(b.date!, today));
  const platform = TIPS.filter((t) => purpose && t.purposes?.includes(purpose));
  const howto = TIPS.filter((t) => t.kind === "howto");
  const law = TIPS.filter((t) => t.kind === "law");
  // 요령과 법을 번갈아 (한 종류만 이어지지 않게)
  const rest = howto.flatMap((h, i) => (law[i] ? [h, law[i]] : [h]));
  return [...season, ...platform, ...rest].slice(0, limit).map(({ purposes, date, ...t }) => t);
}
