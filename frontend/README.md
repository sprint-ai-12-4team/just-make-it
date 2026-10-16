# just-make-it Frontend

소상공인용 AI 광고 이미지 생성 UI (Next.js 15 + TypeScript + Tailwind)

## 페이지 흐름

1. `/` — 목적(매체) 선택
2. `/create` — 정보 입력 + 생성 방식 + 생성 요청
3. `/result` — 결과 확인, 다운로드, 링크 복사, 간단 수정

## 실행

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

브라우저: http://localhost:3000

백엔드(FastAPI)는 `NEXT_PUBLIC_API_URL`(기본 `http://localhost:8000`)로 호출합니다.  
백엔드가 없어도 생성 단계에서 **데모 이미지**로 결과 화면까지 진행됩니다.

## 스택

- Next.js 15 (App Router)
- TypeScript
- Tailwind CSS
- lucide-react (아이콘)

## 백엔드 연동

`lib/api.ts`의 `generateImage()`가 `POST /generate`를 호출합니다.  
API 스펙이 확정되면 필드명만 맞추면 됩니다.

## 폴더 구조

```
frontend/
├── app/
│   ├── page.tsx           # 목적 선택
│   ├── create/page.tsx    # 입력 + 생성
│   └── result/page.tsx    # 결과
├── components/
│   ├── PurposeSelector.tsx
│   ├── InfoForm.tsx
│   ├── GenerationModeSelector.tsx
│   └── ui/
├── lib/
│   ├── api.ts
│   ├── types.ts
│   └── utils.ts
└── package.json
```
