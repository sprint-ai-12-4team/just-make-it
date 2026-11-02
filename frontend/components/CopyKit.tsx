"use client";

import { Chip, FieldError, Notice, RiskyWords } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { checkPost, formatFor, maxLength, postTime } from "@/lib/channels";
import { CONVERT_FORMATS, type Brief, type ConvertFormat, type ConvertResult } from "@/lib/types";
import { Check, Clock, Copy, Loader2, Wand2 } from "lucide-react";
import { useState } from "react";

/** 결과를 복사할 글 한 덩어리로 */
function asText(r: ConvertResult, format: ConvertFormat): string {
  if (typeof r === "string") return r;
  if (Array.isArray(r)) return r.join(format === "instagram_hashtags" ? " " : "\n");
  return `${r.title}\n${r.condition}\n${r.period}`;
}

const CHANNELS = [...new Set(CONVERT_FORMATS.map((f) => f.channel))];

/** 게시 문구 키트: 채널을 고르면 거기에 바로 올릴 글을 만들어 복사 (AI_상담_게시문구키트_제안서 기능 1) */
export function CopyKit({ gid, text, productName, brief }: { gid: string; text: string; productName?: string; brief?: Brief | null }) {
  // 상담에서 채널을 정했으면 그 채널 글부터
  const [format, setFormat] = useState<ConvertFormat>(formatFor(brief?.channel));
  const [area, setArea] = useState("");
  const [discount, setDiscount] = useState("");
  const [until, setUntil] = useState(brief?.period ?? "");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  const channel = CONVERT_FORMATS.find((f) => f.id === format)!.channel;
  const max = maxLength(format);
  const warnings = checkPost(format, result);

  async function make() {
    setBusy(true);
    setError("");
    setResult("");
    try {
      // 숫자(할인율·기간)는 사장님이 적은 것만 보냄. 모델이 지어내지 않게
      const facts = format === "naver_coupon" ? Object.fromEntries(Object.entries({ discount, until }).filter(([, v]) => v.trim())) : undefined;
      const r = await api.convertCopy({ text, format, product_name: productName, area: format === "instagram_location" ? area.trim() || undefined : undefined, facts });
      setResult(asText(r.result, format));
    } catch (e) {
      setError(e instanceof ApiError && (e.status === 404 || e.status === 405) ? "이 기능은 곧 열려요." : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    await navigator.clipboard.writeText(result);
    api.logEvent(gid, "copy_kit", { format, edited_len: result.length });
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <section className="card flex flex-col gap-5">
      <h2 className="text-h-sm font-bold">게시 문구 만들기</h2>
      <p className="-mt-3 hint">“{text}”로 올릴 곳에 맞는 글을 만들어 드려요. 고친 뒤 복사해서 붙여 넣으세요.</p>
      {CHANNELS.map((ch) => (
        <fieldset key={ch}>
          <legend className="label">{ch}</legend>
          <div className="flex flex-wrap gap-2">
            {CONVERT_FORMATS.filter((f) => f.channel === ch).map((f) => (
              <Chip key={f.id} on={format === f.id} onClick={() => (setFormat(f.id), setResult(""))}>
                {f.title}
              </Chip>
            ))}
          </div>
        </fieldset>
      ))}
      {format === "instagram_location" && (
        <div>
          <label htmlFor="ck-area" className="label">
            동네 이름
          </label>
          <input id="ck-area" className="field" value={area} onChange={(e) => setArea(e.target.value)} placeholder="예: 망원동" />
          <p className="mt-2 hint">후보 단어만 드려요. 실제 위치 태그는 인스타 앱에서 골라 주세요.</p>
        </div>
      )}
      {format === "naver_coupon" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="ck-discount" className="label">
              할인 (선택)
            </label>
            <input id="ck-discount" className="field" value={discount} onChange={(e) => setDiscount(e.target.value)} placeholder="예: 10%, 1+1" />
          </div>
          <div>
            <label htmlFor="ck-until" className="label">
              언제까지 (선택)
            </label>
            <input id="ck-until" className="field" value={until} onChange={(e) => setUntil(e.target.value)} placeholder="예: 11월 30일" />
          </div>
        </div>
      )}
      <p className="flex items-start gap-2">
        <Clock aria-hidden className="mt-0.5 size-5 shrink-0" />
        <span>
          <span className="font-semibold">올리기 좋은 시간</span> {postTime(brief?.category, channel)}
        </span>
      </p>
      <button type="button" className="btn-line" disabled={busy} onClick={make}>
        {busy ? <Loader2 aria-hidden className="size-5 animate-spin" /> : <Wand2 aria-hidden className="size-5" />}
        {busy ? "만드는 중" : result ? "다시 만들기" : "글 만들기"}
      </button>
      {error && <Notice>{error}</Notice>}
      {result && (
        <div className="flex flex-col gap-3">
          <label htmlFor="ck-result" className="sr-only">
            만든 글 (고칠 수 있어요)
          </label>
          <textarea
            id="ck-result"
            className="field min-h-[160px] py-3"
            value={result}
            onChange={(e) => setResult(e.target.value)}
            aria-describedby="ck-count"
          />
          <p id="ck-count" className="hint -mt-1 text-right">
            {result.length.toLocaleString()}자{max ? ` / 최대 ${max.toLocaleString()}자` : ""}
          </p>
          {warnings.map((w) => (
            <FieldError key={w}>{w}</FieldError>
          ))}
          <RiskyWords text={result} />
          <button type="button" className="btn-fill" onClick={copy}>
            {copied ? <Check aria-hidden className="size-5" /> : <Copy aria-hidden className="size-5" />}
            {copied ? "복사했어요" : "복사하기"}
          </button>
        </div>
      )}
    </section>
  );
}
