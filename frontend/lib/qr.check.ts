// 실행: node lib/qr.check.ts  (QR 위치 무늬·로고 자리·그림 밖으로 안 나가기)
import assert from "node:assert/strict";
import { clampPlace, inFinder, logoCells } from "./qr.ts";

assert.ok(inFinder(0, 0, 21) && inFinder(6, 20, 21) && inFinder(20, 6, 21));
assert.ok(!inFinder(20, 20, 21) && !inFinder(10, 10, 21) && !inFinder(7, 0, 21));
for (const n of [21, 25, 29, 33, 57]) assert.equal(logoCells(n) % 2, 1);
assert.deepEqual(clampPlace({ x: 0.95, y: -1, w: 0.2 }, 1), { x: 0.8, y: 0, w: 0.2 });
// 세로가 가로의 1.5배면 QR 높이 비율은 w/1.5
assert.deepEqual(clampPlace({ x: 0, y: 2, w: 0.3 }, 1.5), { x: 0, y: 0.8, w: 0.3 });
console.log("qr ok");
