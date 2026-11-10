// 실행: node lib/tips.check.ts  (대기 카드 고르기 검사)
import assert from "node:assert/strict";
import { daysUntil, pickTips } from "./tips.ts";

const nov2 = new Date(2026, 10, 2);
assert.equal(daysUntil("11-11", nov2), 9);
assert.equal(daysUntil("11-02", nov2), 0);
assert.equal(daysUntil("02-14", nov2), 104); // 내년
// 11월 2일: 빼빼로데이가 맨 앞, 크리스마스(53일 뒤)는 아직 안 보임
const t = pickTips("kakao", nov2);
assert.equal(t[0].id, "season-1111");
assert.ok(!t.some((x) => x.id === "season-1225"));
// 카카오면 (광고) 표시 카드, 다른 목적 카드는 없음
assert.ok(t.some((x) => x.id === "platform-kakao-ad"));
assert.ok(!t.some((x) => x.id.startsWith("platform-yt")));
assert.equal(t.length, 6);
// 목적을 모르면 공통 카드만
assert.ok(pickTips(undefined, nov2).every((x) => x.kind !== "platform"));
console.log("tips ok");
