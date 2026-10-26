// 실행: node lib/family.check.ts  (같은 원본 계열 찾기 검사)
import assert from "node:assert/strict";
import { familyIds, type Family } from "./family.ts";

const e = (parent: string | null, at: number) => ({ parent, img: "", at });
// a → b → c, a → d / 따로 만든 x / 부모를 모르는 y(부모 z는 기억 안 함)
const map: Family = { a: e(null, 1), b: e("a", 2), c: e("b", 3), d: e("a", 4), x: e(null, 5), y: e("z", 6) };

assert.deepEqual(familyIds(map, "c"), ["a", "b", "c", "d"]);
assert.deepEqual(familyIds(map, "a"), ["a", "b", "c", "d"]);
assert.deepEqual(familyIds(map, "x"), ["x"]);
assert.deepEqual(familyIds(map, "y"), ["y"]);
// 순환(실제로는 생기지 않음)이 있어도 멈춤
assert.ok(familyIds({ p: e("q", 1), q: e("p", 2) }, "p").length >= 1);
console.log("family ok");
