// 실행: node lib/draw.check.ts  (글자 수 = 너비로 보고 줄바꿈 검사)
import assert from "node:assert/strict";
import { wrap } from "./draw.ts";

const len = (s: string) => s.length;
assert.deepEqual(wrap(len, "주말 20% 할인", 20), ["주말 20% 할인"]);
assert.deepEqual(wrap(len, "주말 20% 할인", 6), ["주말 20%", "할인"]);
assert.deepEqual(wrap(len, "띄어쓰기없는긴문장", 4), ["띄어쓰기", "없는긴문", "장"]);
assert.deepEqual(wrap(len, "첫줄\n둘째줄", 10), ["첫줄", "둘째줄"]);
assert.deepEqual(wrap(len, "", 10), [""]);
console.log("wrap ok");
