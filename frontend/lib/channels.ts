// 채널 규칙과 올리기 좋은 시간. 플랫폼이 자주 바꾸므로 모델이 아니라 여기서 맞춤 (제안서 '안전장치')
// ponytail: 고정 표. 바뀌면 이 파일만 고치기. [확인] = 공식 도움말로 다시 볼 것
import type { ConvertFormat } from "./types";

const RULES: Partial<Record<ConvertFormat, { max?: number; tags?: number }>> = {
  instagram_post: { max: 2200 }, // 인스타 캡션 최대 2,200자
  instagram_hashtags: { tags: 30 }, // 게시물당 해시태그 최대 30개
};

export const maxLength = (f: ConvertFormat) => RULES[f]?.max;

/** 올리기 전에 알려 줄 것 (막지는 않음). 과장 표현(S6)은 화면에서 RiskyWords로 따로 */
export function checkPost(f: ConvertFormat, text: string): string[] {
  const r = RULES[f] ?? {};
  const out: string[] = [];
  if (r.max && text.length > r.max) out.push(`${r.max.toLocaleString()}자를 넘어요. 조금 줄여 주세요.`);
  const tags = text.match(/#\S+/g)?.length ?? 0;
  if (r.tags && tags > r.tags) out.push(`해시태그는 ${r.tags}개까지 넣을 수 있어요.`);
  return out;
}

// [확인] 업종별 대략적인 시간. 인터뷰(owner_interview B4)로 다시 정하기
const BY_CATEGORY: Record<string, string> = {
  카페: "아침 7~9시 출근길, 오후 2~4시 쉬는 시간",
  음식점: "점심 전 10~11시, 저녁 전 4~5시",
  미용: "저녁 8~10시 (예약을 정하는 시간)",
  꽃집: "기념일 3~5일 전 저녁",
  옷가게: "저녁 8~10시, 주말 오전",
};

/** 올리기 좋은 시간 한 줄. 카톡은 밤 광고 메시지 규칙을 같이 알림 */
export function postTime(category?: string, channel?: string): string {
  const t = BY_CATEGORY[category ?? ""] ?? "손님이 가게를 떠올리기 1~2시간 전";
  // 정보통신망법 50조: 밤 9시~아침 8시 광고 메시지는 별도 동의가 필요
  return channel?.includes("카카오") ? `${t} · 밤 9시~아침 8시에는 보내지 않기` : t;
}

/** 상담에서 정한 채널 → 먼저 보여 줄 형식 */
export function formatFor(channel?: string): ConvertFormat {
  if (!channel) return "instagram_post";
  if (channel.includes("네이버")) return "naver_coupon";
  if (/스마트스토어|쿠팡/.test(channel)) return "store_description";
  return "instagram_post";
}
