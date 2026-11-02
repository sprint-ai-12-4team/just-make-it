// 실행: node lib/adCheck.check.ts  (조심할 광고 표현 찾기 검사)
import assert from "node:assert/strict";
import { riskyWords } from "./adCheck.ts";

assert.deepEqual(riskyWords("주말 20% 할인"), []);
assert.deepEqual(riskyWords("동네 1위 빵집, 맛 보장"), ["1위", "보장"]);
assert.deepEqual(riskyWords("NO.1 수제잼"), ["No.1"]);
assert.deepEqual(riskyWords("최고 최고"), ["최고"]);
console.log("adCheck ok");
