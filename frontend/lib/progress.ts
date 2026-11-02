// 진행 막대 계산 (service_consulting.md A-4). 화면과 떨어뜨려 node로 검사함
import type { GenProgress } from "./types";

const MAX = 95; // 끝나기 전에는 꽉 채우지 않음

/** 접수 후 지난 시간(ms). 서버 값 → 서버 접수 시각 → 화면을 연 시각 순서로 믿음 */
export function elapsedMs(now: number, opened: number, createdAt?: string, server?: { elapsed: number; at: number }): number {
  if (server) return server.elapsed * 1000 + (now - server.at);
  const t = createdAt ? Date.parse(createdAt) : NaN;
  // PC 시계가 틀려 미래이거나 1시간 넘게 지난 값이면 믿지 않음
  if (Number.isFinite(t) && t <= now && now - t < 3_600_000) return now - t;
  return now - opened;
}

/** 다음 막대 %. 줄어들지 않고, 예상보다 늦으면 95%까지 천천히 다가감 */
export function nextPercent(prev: number, elapsed: number, left: number | null, p?: GenProgress | null): number {
  if (left === null) return prev;
  let pct = left > 0 ? (100 * elapsed) / (elapsed + left) : prev + (MAX - prev) * 0.03;
  // 그림 단계를 알면 그만큼은 채움: 문구 15% + 그림 75%
  if (p?.step != null && p.steps) pct = Math.max(pct, 15 + (75 * p.step) / p.steps);
  else if (p?.phase === "image") pct = Math.max(pct, 15);
  else if (p?.phase === "saving") pct = Math.max(pct, 90);
  return Math.min(MAX, Math.max(prev, pct));
}

/** 막대 아래 문구 */
export function statusText(p: GenProgress | null | undefined, overdue: boolean): string {
  if (p?.stage === "queued") return p.jobs_ahead > 0 ? `앞에 ${p.jobs_ahead}건 기다리는 중` : "곧 시작해요";
  if (overdue) return "생각보다 조금 더 걸리고 있어요";
  if (p?.phase === "text") return "문구를 다듬고 있어요";
  if (p?.phase === "saving") return "다 그렸어요. 저장하고 있어요";
  if (p?.step != null && p.steps) return `그림을 그리고 있어요 (${p.step}/${p.steps})`;
  return "그림을 그리고 있어요";
}
