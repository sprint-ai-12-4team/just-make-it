// 실행: node lib/cutout.check.ts  (Magic Wand 영역 채우기 검사)
import assert from "node:assert/strict";
import { floodFill } from "./cutout.ts";

// 4x2 사진: 왼쪽 2칸 흰색, 오른쪽 2칸 검정
const W = [255, 255, 255, 255];
const B = [0, 0, 0, 255];
const rgba = [W, W, B, B, W, W, B, B].flat();
const full = new Uint8ClampedArray(8).fill(255);

// 흰색을 누르면 흰 영역만 지워짐, 원래 마스크는 그대로
const erased = floodFill(rgba, full, 4, 2, 0, 0, 0);
assert.deepEqual([...erased], [0, 0, 255, 255, 0, 0, 255, 255]);
assert.deepEqual([...full], [255, 255, 255, 255, 255, 255, 255, 255]);

// 되살리기: 지운 곳도 원본 색으로 찾아서 복원
assert.deepEqual([...floodFill(rgba, erased, 4, 2, 1, 1, 255)], [...full]);

// 오른쪽 끝에서 다음 줄 왼쪽으로 넘어가지 않음 (가로 4칸, 회색 띠가 끊겨 있음)
const G = [128, 128, 128, 255];
const wrapCase = [B, B, B, G, G, B, B, B].flat();
assert.deepEqual([...floodFill(wrapCase, full, 4, 2, 3, 0, 0)], [255, 255, 255, 0, 255, 255, 255, 255]);

// 허용 오차 안의 비슷한 색은 같은 영역
const near = [[250, 250, 250, 255], W, B, B].flat();
assert.deepEqual([...floodFill(near, new Uint8ClampedArray(4).fill(255), 4, 1, 1, 0, 0)], [0, 0, 255, 255]);
console.log("floodFill ok");
