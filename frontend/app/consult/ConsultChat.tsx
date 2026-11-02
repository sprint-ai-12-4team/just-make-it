"use client";

import { Chip, Notice, Steps } from "@/components/ui";
import { postTime } from "@/lib/channels";
import { api, ApiError } from "@/lib/api";
import type { Brief, ConsultMessage, ConsultTurn, Purpose } from "@/lib/types";
import { PURPOSES } from "@/lib/types";
import clsx from "clsx";
import { ArrowRight, Loader2, PencilLine, Send } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

const MAX_TEXT = 500; // api_spec_consult 3-2

/** Phase 1: AI 광고 상담. 끝나면 기획서 → 만들기 화면(Phase 2)을 미리 채움 */
export function ConsultChat({ initialId, purpose, productName }: { initialId?: string; purpose?: Purpose; productName?: string }) {
  const [id, setId] = useState(initialId ?? "");
  const [messages, setMessages] = useState<ConsultMessage[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [free, setFree] = useState(true);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [editsLeft, setEditsLeft] = useState<number | undefined>();
  const [ended, setEnded] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [unavailable, setUnavailable] = useState(false);
  const started = useRef(false);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const apply = (t: ConsultTurn) => {
    setMessages((m) => [...m, { role: "assistant", text: t.reply, chips: t.chips }]);
    setChips(t.chips);
    setFree(t.allow_free_text);
    setBrief(t.brief);
    setEditsLeft(t.edits_left);
    setEnded(!!t.ended || t.turn >= t.max_turns);
  };

  // 처음: 주소에 id가 있으면 이어서, 없으면 새로 시작. 서버에 상담이 없으면(404) 안내만
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const job = initialId
      ? api.getConsult(initialId).then((c) => {
          setMessages(c.messages);
          const last = [...c.messages].reverse().find((m) => m.role === "assistant");
          setChips(c.brief ? [] : (last?.chips ?? []));
          setBrief(c.brief);
          setEditsLeft(c.edits_left);
          setEnded(!!c.ended);
        })
      : api.startConsult({ purpose, product_name: productName }).then((t) => {
          setId(t.id);
          // 새로고침해도 이어지게 주소에 id를 남김 (화면은 다시 그리지 않음)
          history.replaceState(null, "", `/consult?id=${t.id}`);
          apply(t);
        });
    job
      .catch((e) => {
        if (e instanceof ApiError && (e.status === 404 || e.status === 405)) setUnavailable(true);
        else setError((e as Error).message);
      })
      .finally(() => setBusy(false));
  }, [initialId, purpose, productName]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [messages, busy]);

  async function send(value: string, chip: boolean) {
    const v = value.trim();
    if (!v || busy || !id) return;
    setMessages((m) => [...m, { role: "user", text: v }]);
    setText("");
    setChips([]);
    setBusy(true);
    setError("");
    try {
      apply(await api.sendConsult(id, v, chip));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setEnded(true);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (unavailable)
    return (
      <div className="flex flex-col gap-6 pt-4">
        <Steps current={1} />
        <Notice action={<Link href="/#start" className="btn-fill">바로 만들기</Link>}>AI 상담은 곧 열려요. 지금은 바로 만들 수 있어요.</Notice>
      </div>
    );

  const canType = free && !ended && !busy;

  return (
    <div className="flex flex-col gap-6 pt-4">
      <div className="flex flex-col gap-3">
        <Steps current={1} />
        <h1 className="text-h font-bold">광고, 같이 정해 볼까요?</h1>
        <p className="hint">질문 몇 개에 답하면 문구와 올릴 곳을 정리해 드려요. 고르기만 해도 돼요.</p>
      </div>

      <div role="log" aria-label="상담 내용" className="flex flex-col gap-3">
        {messages.map((m, i) => (
          <p
            key={i}
            className={clsx("max-w-[85%] whitespace-pre-line rounded-card px-5 py-4", m.role === "assistant" ? "self-start bg-mist" : "self-end bg-pollen")}
          >
            <span className="sr-only">{m.role === "assistant" ? "도우미: " : "나: "}</span>
            {m.text}
          </p>
        ))}
        {busy && (
          <p className="flex items-center gap-2 self-start rounded-card bg-mist px-5 py-4 text-graphite">
            <Loader2 aria-hidden className="size-5 animate-spin" /> 생각하고 있어요
          </p>
        )}
        <div ref={end} />
      </div>

      {chips.length > 0 && !busy && !ended && (
        <div role="group" aria-label="눌러서 답하기" className="flex flex-wrap gap-2">
          {chips.map((c) => (
            <Chip key={c} on={false} onClick={() => send(c, true)}>
              {c}
            </Chip>
          ))}
        </div>
      )}

      {error && <Notice>{error}</Notice>}

      {brief && <BriefCard id={id} brief={brief} editsLeft={ended ? 0 : editsLeft} onEdit={() => input.current?.focus()} />}

      {ended && !brief && (
        <Notice action={<Link href="/#start" className="btn-fill">바로 만들기</Link>}>상담을 마쳤어요. 이제 바로 만들어 볼까요?</Notice>
      )}

      {free && !ended && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(text, false);
          }}
          // 기획서가 나온 뒤에는 고정하지 않음 (휴대폰에서 기획서를 가리지 않게)
          className={clsx("-mx-4 flex flex-col gap-1 bg-white/95 px-4 py-4", !brief && "sticky bottom-0")}
        >
          <label htmlFor="say" className="sr-only">
            직접 적어서 답하기
          </label>
          <div className="flex gap-2">
            <input
              id="say"
              ref={input}
              className="field"
              value={text}
              maxLength={MAX_TEXT}
              disabled={!canType}
              onChange={(e) => setText(e.target.value)}
              placeholder={chips.length ? "고르거나 직접 적어 주세요" : "직접 적어 주세요"}
              aria-describedby="say-count"
            />
            <button type="submit" className="btn-fill shrink-0 px-5" disabled={!canType || !text.trim()} aria-label="보내기">
              <Send aria-hidden className="size-5" />
            </button>
          </div>
          <p id="say-count" className="hint text-right">
            {text.length} / {MAX_TEXT}
          </p>
        </form>
      )}

      <Link href="/#start" className="-mt-2 inline-flex min-h-[44px] items-center gap-1 self-start rounded-btn hint underline underline-offset-4">
        상담 없이 바로 만들기
      </Link>
    </div>
  );
}

/** 상담 결과 = 광고 기획서. 문구 2안 중 하나를 골라 만들기 화면으로 넘기면 칸이 채워짐 */
function BriefCard({ id, brief, editsLeft, onEdit }: { id: string; brief: Brief; editsLeft?: number; onEdit: () => void }) {
  const [pick, setPick] = useState(0);
  const purposeTitle = PURPOSES.find((p) => p.id === brief.purpose)?.title;
  const rows: [string, string][] = [
    ["가게", brief.category],
    ["알릴 것", `${brief.goal} · ${brief.product_name}`],
    ...(brief.period ? ([["기간", brief.period]] as [string, string][]) : []),
    ["손님이 좋아하는 점", brief.strengths.join(", ") || "아직 몰라요"],
    ["주로 오는 손님", brief.audience],
    ["핵심 메시지", brief.message],
    ["올릴 곳", brief.channel],
    ["올리기 좋은 시간", postTime(brief.category, brief.channel)],
    ["느낌", brief.style ?? "알아서"],
    ["이렇게 제안하는 이유", brief.reason],
  ];
  const copies = brief.copies.length ? brief.copies : [brief.message];
  return (
    <section aria-labelledby="brief-title" className="flex flex-col gap-5 rounded-card bg-honey p-6 sm:p-8">
      <h2 id="brief-title" className="text-h-sm font-bold">
        광고 기획서
      </h2>
      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-[auto_1fr]">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="font-semibold">{k}</dt>
            <dd className="-mt-2 sm:mt-0">{v}</dd>
          </div>
        ))}
      </dl>
      <fieldset>
        <legend className="label">그림에 넣을 문구를 골라 주세요</legend>
        <div className="flex flex-wrap gap-2">
          {copies.map((c, i) => (
            <Chip key={c} on={pick === i} onClick={() => setPick(i)}>
              {c}
            </Chip>
          ))}
        </div>
      </fieldset>
      {brief.purpose === "free" && purposeTitle && <p className="hint text-ink">{brief.channel}에 맞는 크기가 아직 없어서 ‘{purposeTitle}’로 만들어요.</p>}
      {brief.next_tips.length > 0 && (
        <ul className="list-disc pl-5">
          {brief.next_tips.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Link href={`/create?purpose=${brief.purpose}&consult=${id}&copy=${pick}`} className="btn-fill">
          이 내용으로 이미지 만들기 <ArrowRight aria-hidden className="size-5" />
        </Link>
        {editsLeft !== 0 && (
          <button type="button" className="btn bg-white hover:bg-mist" onClick={onEdit}>
            <PencilLine aria-hidden className="size-5" /> 조금 고칠래요{editsLeft ? ` (${editsLeft}번 남음)` : ""}
          </button>
        )}
      </div>
    </section>
  );
}
