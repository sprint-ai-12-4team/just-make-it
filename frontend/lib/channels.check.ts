// node lib/channels.check.ts
import assert from "node:assert/strict";
import { checkPost, formatFor, postTime } from "./channels.ts";

assert.deepEqual(checkPost("instagram_post", "가을 신메뉴 나왔어요"), []);
assert.equal(checkPost("instagram_post", "가".repeat(2201)).length, 1);
assert.equal(checkPost("instagram_hashtags", Array.from({ length: 31 }, (_, i) => `#t${i}`).join(" ")).length, 1);
assert.equal(formatFor("네이버 플레이스"), "naver_coupon");
assert.equal(formatFor("쿠팡"), "store_description");
assert.equal(formatFor(undefined), "instagram_post");
assert.match(postTime("카페", "카카오톡"), /밤 9시/);
assert.doesNotMatch(postTime("카페", "인스타그램"), /밤 9시/);
console.log("channels ok");
