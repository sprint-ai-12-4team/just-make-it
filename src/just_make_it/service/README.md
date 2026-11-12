# service — 소상공인 UX를 맡는 층

> 원칙: **사장님이 디자인 용어를 몰라도, 한 번에 올릴 수 있는 광고를 받는다.**
> 모델(`core/`)은 그림을 만들고, 서빙(`serving/`)은 길을 고른다. service와 프론트는 "만든 뒤 쓰기까지"를 맡는다.
> API 계약: `docs/api_spec.md` · 흐름: `docs/product/user_flow.md`

## BE (`src/just_make_it/service/`)

| 파일 | 하는 일 | UX에서 의미 |
|------|---------|-------------|
| `db.py` · `schema.sql` | 생성·상세페이지·상담·사용 기록 (VM 로컬 SQLite) | 새로고침·다른 기기·공유 링크에서도 같은 결과. `parent_id`로 "같은 원본에서 만든 결과" 되돌리기 |
| `storage.py` | 이미지 디스크 저장, 영구 URL (`/images/...`) | 링크 하나로 직원·손님에게 바로 공유. 글자 없는 원본(`background`)도 보관 → 글자만 다시 고치기 |
| `tips.py` | 기다리는 동안 보여 줄 정보 카드 (`GET /tips`) | 20~40초 대기를 시즌 일정·올리기 요령·광고법 안내로 채움 |
| `gcs_storage.py` · `user_auth.py` | 비어 있음 (예정) | 지금은 로그인 없이 `X-Client-Id`(브라우저 익명 ID)로 구분 |

테이블: `generations` · `detail_pages` · `events`(다운로드·링크 복사·다시 만들기 → 채택률) · `consults`/`advices`(AI 상담) · `text_calls`(문구 호출·비용) · `flags`(악용 감지)

## FE (`frontend/`)

흐름: **상담(선택) → 입력 → 기다리기 → 결과에서 다듬기 → 올리기**

| 단계 | 기능 | 파일 |
|------|------|------|
| 상담 | 칩으로 답하면 기획서가 나오고 입력이 채워짐 | `app/consult/` |
| 입력 | 목적(인스타·쿠팡·유튜브…)만 고르면 크기 자동, 문구 추천, 견본 카드, 무료 사진 고르기, 상품 사진 배경 지우기(브라우저 BiRefNet) | `app/create/`, `lib/cutout.ts`, `lib/samples.ts` |
| 기다리기 | 남은 시간·앞 대기 수, 정보 카드 | `components/GenProgress.tsx`, `lib/progress.ts` |
| 다듬기 | 글자 직접 고치기(위치·글꼴·단어별 색), **AI로 글자 꾸미기**(11-11), 배경 지우고 색 채우기, "더 밝게" 같은 칩으로 다시 만들기, 빠르게/더 정교하게 | `app/result/[id]/`, `components/TextCanvas.tsx` |
| 올리기 | 저장·링크, QR 넣기, 채널별 게시 문구(인스타 본문·쿠폰·블로그 제목), 플랫폼에서 가려지는 곳 표시 | `components/CopyKit.tsx`, `components/QrStamp.tsx`, `lib/channels.ts` |
| 안전 | 과장 표현(최고·100% 등) 알려 주기 — 막지 않음 | `lib/adCheck.ts` |
| 상세페이지 | 커머스용 5칸, 칸마다 다시 만들기 | `app/detail/[id]/` |
| 지표 | 채택률·직접 고침 비율 (발표·운영) | `app/stats/` |

## 지킬 것

- **화면 말투**: 쉬운 우리말, 기술 용어 금지 (`klein`·`OpenAI`·`source`를 노출하지 않음 → "빠르게 / 더 정교하게")
- **오류는 다음 행동과 함께**: "잠시 후 다시 시도해 주세요", "다시 만들기" 버튼. 서버 `detail` 문구를 그대로 보여 줌
- **원본은 지우지 않는다**: 다시 만들기·꾸미기는 새 결과(`parent_id`)로 → 언제든 되돌리기
- **한도**: OpenAI 팀 한도 $30. 테스트는 `NEXT_PUBLIC_MOCK=1`(프론트)·mock 생성기(서버)로
- **경계**: 모델 로드·추론은 `core/`, 대기열·Fallback은 `serving/`. service는 DB·저장·비즈니스 규칙만
