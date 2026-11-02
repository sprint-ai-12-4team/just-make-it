// 실행: node lib/progress.check.ts  (진행 막대 계산 검사)
import assert from "node:assert/strict";
import { elapsedMs, nextPercent, statusText } from "./progress.ts";

const now = 1_000_000_000;
// 새로고침해도 서버 접수 시각부터 셈 (P1)
assert.equal(elapsedMs(now, now, new Date(now - 10_000).toISOString()), 10_000);
// 서버 elapsed가 있으면 그것 + 받은 뒤 지난 시간
assert.equal(elapsedMs(now, now, undefined, { elapsed: 5, at: now - 1000 }), 6000);
// 미래 시각(PC 시계 틀림)은 화면을 연 시각으로
assert.equal(elapsedMs(now, now - 2000, new Date(now + 60_000).toISOString()), 2000);

// 절반 지남 → 50%, 줄어들지 않음, 95% 넘지 않음
assert.equal(nextPercent(0, 10, 10), 50);
assert.equal(nextPercent(60, 10, 10), 60);
assert.equal(nextPercent(0, 1000, 1), 95);
// 예상보다 늦으면 조금씩만 오름 (P3)
const late = nextPercent(80, 30, 0);
assert.ok(late > 80 && late < 95);
// 그림 2/4단계면 최소 52.5%
assert.equal(nextPercent(0, 1, 100, { stage: "running", jobs_ahead: 0, estimated_seconds: 1, step: 2, steps: 4 }), 52.5);
// 남은 시간을 모르면 그대로
assert.equal(nextPercent(30, 5, null), 30);

assert.equal(statusText({ stage: "queued", jobs_ahead: 2, estimated_seconds: 1 }, false), "앞에 2건 기다리는 중");
assert.equal(statusText({ stage: "running", jobs_ahead: 0, estimated_seconds: 0 }, true), "생각보다 조금 더 걸리고 있어요");
console.log("progress ok");
