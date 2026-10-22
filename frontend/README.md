# just-make-it Frontend

Next.js 15 + TypeScript + Tailwind 3. 디자인 토큰은 루트 `DESIGN.md` (먹색 + 노랑, 다른 색 추가 금지). API 계약은 `docs/api_spec.md`.

```bash
cp .env.example .env.local   # NEXT_PUBLIC_MOCK=1 이면 서버 없이 가짜 응답
npm install && npm run dev   # http://localhost:3000
node lib/draw.check.ts       # 문구 줄바꿈 검사
```

| 경로 | 화면 |
|------|------|
| `/` | ① 어디에 올릴지 고르기 |
| `/create?purpose=` | ② 이름·하고 싶은 말·문구 추천·느낌·사진 → 생성 |
| `/result/[id]` | 결과. 글자 고치기(즉시 반영)·저장·링크 복사·다시 만들기 |
| `/detail/[id]` | 상세페이지 진행(2초 폴링)·섹션 재생성·긴 이미지 한 장 저장 |

- 이미지는 글자 없이 생성 → `lib/draw.ts`가 `<canvas>`에 문구를 얹음. 미리보기와 저장이 같은 코드
- 저장소(`image_url`)에 CORS 허용이 없으면 저장이 실패함
- `lib/mock.ts`는 서빙 연결 후 삭제
