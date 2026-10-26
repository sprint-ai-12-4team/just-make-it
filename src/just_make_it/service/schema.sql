-- 앱 시작 시 한 번 실행. WAL은 DB 파일에 저장되지만 foreign_keys는 연결마다 켜야 함
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 상세페이지 1건. 섹션 이미지는 generations 행으로 저장 (재생성·모델 교체·기록을 단일 이미지와 같은 코드로 처리)
-- 섹션의 현재 결과 = 같은 (detail_page_id, section_index) 중 created_at이 가장 최근인 행. 이전 행은 기록으로 남음
CREATE TABLE IF NOT EXISTS detail_pages (
    id            TEXT PRIMARY KEY,                 -- uuid4
    client_id     TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    input_json    TEXT NOT NULL CHECK (json_valid(input_json)),   -- product_name, message, features, style, reference_image_path
    sections_json TEXT CHECK (sections_json IS NULL OR json_valid(sections_json)),  -- [{role, title, body, image_prompt}] 텍스트 모델 결과
    status        TEXT NOT NULL CHECK (status IN ('processing', 'success', 'error')),
    error         TEXT,
    text_ms       INTEGER,
    CHECK (status != 'error' OR error IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_detail_pages_client
    ON detail_pages (client_id, created_at DESC);

CREATE TABLE IF NOT EXISTS generations (
    id            TEXT PRIMARY KEY,                 -- uuid4. 서빙 job_id와 같은 값을 씁니다
    client_id     TEXT NOT NULL,                    -- 브라우저별 익명 ID
    parent_id     TEXT REFERENCES generations(id),  -- "이 결과로 다시 생성"한 원본
    detail_page_id TEXT REFERENCES detail_pages(id),  -- 상세페이지 섹션이면 값 있음. 단일 이미지는 NULL
    section_index INTEGER,                          -- 0부터. detail_page_id와 함께만 씀
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    -- 입력
    purpose       TEXT NOT NULL,                    -- [변경] CHECK 제거, 값 검사는 API(api_spec 5장)
    input_json    TEXT NOT NULL CHECK (json_valid(input_json)),   -- product_name, message, generation_mode, style, adjustments, reference_image_path

    -- 출력
    copy_json     TEXT CHECK (copy_json IS NULL OR json_valid(copy_json)),
    image_prompt  TEXT,
    image_path    TEXT,                             -- 모든 결과 저장

    -- 재현 조건
    backend       TEXT NOT NULL CHECK (backend IN ('local', 'openai', 'mock')),  -- [변경] mock 허용
    route         TEXT NOT NULL DEFAULT 'primary'
                  CHECK (route IN ('primary', 'fallback', 'premium')),    -- [추가] 서빙이 고른 경로
    model         TEXT NOT NULL,
    model_version TEXT,
    seed          INTEGER,                          -- OpenAI는 NULL
    params_json   TEXT CHECK (params_json IS NULL OR json_valid(params_json)),  -- text_model, quality, 해상도, steps 등

    -- 평가·운영
    status        TEXT NOT NULL CHECK (status IN ('processing', 'success', 'error')),  -- PM API 스펙과 같음
    error         TEXT,
    queue_ms      INTEGER,                          -- [추가] 대기열 대기 시간
    text_ms       INTEGER,                          -- 문구 생성 소요
    image_ms      INTEGER,                          -- 이미지 생성 소요
    cost_usd      REAL,                             -- OpenAI 호출 비용 (문구 + 이미지)
    downloaded_at TEXT,                             -- 첫 다운로드·링크 복사 시각

    CHECK (status != 'success' OR image_path IS NOT NULL),  -- 성공한 결과는 반드시 이미지가 있음
    CHECK (status != 'error' OR error IS NOT NULL),         -- [추가] 실패한 결과는 반드시 원인이 있음
    CHECK ((detail_page_id IS NULL) = (section_index IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_generations_section
    ON generations (detail_page_id, section_index, created_at DESC) WHERE detail_page_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_generations_client
    ON generations (client_id, created_at DESC);

-- [추가] 서버 시작 시 정리 쿼리가 빨리 찾도록 (processing인 행만 인덱스)
CREATE INDEX IF NOT EXISTS idx_generations_processing
    ON generations (status) WHERE status = 'processing';
-- 사용 기록 (docs/api_spec_next.md 1장). 채택률 지표 + 다음 학습용 선호 데이터
-- type 값 검사는 db.EVENT_TYPES (SQLite는 CHECK를 바꾸려면 테이블을 새로 만들어야 해서)
CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY,
    generation_id TEXT NOT NULL REFERENCES generations(id),
    client_id     TEXT NOT NULL,
    type          TEXT NOT NULL,
    detail_json   TEXT CHECK (detail_json IS NULL OR json_valid(detail_json)),
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_events_generation
    ON events (generation_id, type);
