// 같은 원본에서 다시 만든 결과들을 이 브라우저에 기억 → 서버 목록 API 없이 나란히 보기
// localStorage라 탭을 닫아도 남지만, 다른 기기·공유 링크로 연 사람에게는 안 보임
export interface Entry {
  parent: string | null;
  img: string;
  at: number;
}
export type Family = Record<string, Entry>;

const KEY = "jmi_family";
const MAX = 100; // ponytail: 오래된 것부터 버림. 서버 목록 API가 생기면 이 파일째 대체

/** 맨 처음 원본 id (부모를 기억하는 데까지 거슬러 올라감) */
function rootOf(map: Family, id: string): string {
  const seen = new Set<string>();
  while (map[id]?.parent && map[map[id].parent!] && !seen.has(id)) {
    seen.add(id);
    id = map[id].parent!;
  }
  return id;
}

/** id와 같은 원본에서 나온 결과 id들 (만든 순서) */
export function familyIds(map: Family, id: string): string[] {
  const root = rootOf(map, id);
  return Object.keys(map)
    .filter((k) => rootOf(map, k) === root)
    .sort((a, b) => map[a].at - map[b].at);
}

function load(): Family {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}");
  } catch {
    return {};
  }
}

/** 결과를 기억하고, 같은 원본 계열을 돌려줌 */
export function remember(id: string, parent: string | null | undefined, img: string): { id: string; img: string }[] {
  const map = load();
  map[id] ??= { parent: parent ?? null, img, at: Date.now() };
  const keep = Object.keys(map).sort((a, b) => map[b].at - map[a].at).slice(0, MAX);
  const kept: Family = Object.fromEntries(keep.map((k) => [k, map[k]]));
  try {
    localStorage.setItem(KEY, JSON.stringify(kept));
  } catch {}
  return familyIds(kept, id).map((k) => ({ id: k, img: kept[k].img }));
}
