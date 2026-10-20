-- 앱 시작 시 한 번 실행. WAL은 DB 파일에 저장되지만 foreign_keys는 연결마다 켜야 함
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS generations (
    id            TEXT PRIMARY KEY,                 -- uuid4, URL에 노출돼도 남의 기록을 못 훑도록
    client_id     TEXT NOT NULL,                    -- 브라우저별 익명 ID
    parent_id     TEXT REFERENCES generations(id),  -- "이 결과로 다시 생성"한 원본
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    -- 입력
    purpose       TEXT NOT NULL CHECK (purpose IN ('instagram', 'commerce', 'youtube', 'kakao', 'free')),  -- api_spec 5장
    input_json    TEXT NOT NULL CHECK (json_valid(input_json)),   -- product_name, message, generation_mode, style, adjustments, reference_image_path

    -- 출력
    copy_json     TEXT CHECK (copy_json IS NULL OR json_valid(copy_json)),  -- 필드별 문구
    image_prompt  TEXT,
    image_path    TEXT,                             -- 저장소 내 경로. 모든 결과 저장 (GPU 결과도 seed로 똑같이 재현된다는 보장 없음)

    -- 재현 조건
    backend       TEXT NOT NULL CHECK (backend IN ('local', 'openai')),  -- API 응답의 source
    model         TEXT NOT NULL,                    -- 이미지 모델 이름
    model_version TEXT,                             -- LoRA·체크포인트 버전. 바꾸면 이전 기록은 재현 불가
    seed          INTEGER,                          -- OpenAI는 NULL
    params_json   TEXT CHECK (params_json IS NULL OR json_valid(params_json)),  -- text_model, quality, steps, scheduler, cfg, 해상도, 라이브러리 버전

    -- 평가·운영
    status        TEXT NOT NULL CHECK (status IN ('processing','success','error')),
    error         TEXT,
    text_ms       INTEGER,                          -- 문구 생성 소요
    image_ms      INTEGER,                          -- 이미지 생성 소요
    cost_usd      REAL,                             -- OpenAI 호출 비용 (문구 + 이미지). 로컬은 NULL
    downloaded_at TEXT,                             -- 첫 다운로드·링크 복사 시각. 성공 지표용

    CHECK (status != 'success' OR image_path IS NOT NULL)  -- 성공한 결과는 반드시 이미지가 있음
);

CREATE INDEX IF NOT EXISTS idx_generations_client
    ON generations (client_id, created_at DESC);
