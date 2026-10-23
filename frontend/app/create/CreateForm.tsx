"use client";

import { CutoutEditor } from "@/components/CutoutEditor";
import { Chip, FieldError, Notice, Waiting } from "@/components/ui";
import { api } from "@/lib/api";
import { shrinkPhoto } from "@/lib/draw";
import { saveCopies } from "@/lib/textStyles";
import { IMAGE_MODELS, STYLES, TEXT_MODELS, type ImageModel, type Purpose, type TextModel } from "@/lib/types";
import clsx from "clsx";
import { ChevronLeft, ImagePlus, Scissors, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

const PHOTO_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_PHOTO = 10 * 1024 * 1024;

export function CreateForm({ purpose, purposeTitle }: { purpose: Purpose; purposeTitle: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [style, setStyle] = useState<string | null>(null);
  const [imageModel, setImageModel] = useState<ImageModel>(IMAGE_MODELS[0].id);
  const [textModel, setTextModel] = useState<TextModel>(TEXT_MODELS[0].id);
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoUrl, setPhotoUrl] = useState("");
  const [photoError, setPhotoError] = useState("");
  const [cutout, setCutout] = useState(false);
  const [detail, setDetail] = useState(false);
  const [features, setFeatures] = useState(["", "", ""]);
  const [copies, setCopies] = useState<string[]>([]);
  const [copyBusy, setCopyBusy] = useState(false);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const ready = name.trim() && message.trim();

  async function pickPhoto(file: File | undefined) {
    setPhotoError("");
    if (!file) return;
    if (!PHOTO_TYPES.includes(file.type)) return setPhotoError("PNG, JPG, WEBP 사진만 올릴 수 있어요.");
    // 휴대폰 원본은 10MB를 넘기 쉬움 → 줄인 뒤의 크기로 검사
    file = await shrinkPhoto(file).catch(() => file!);
    if (file.size > MAX_PHOTO) return setPhotoError("사진은 10MB 이하로 올려 주세요.");
    if (photoUrl) URL.revokeObjectURL(photoUrl); // 배경 지운 사진으로 바꿀 때 이전 사진 해제
    setCutout(false);
    setPhoto(file);
    setPhotoUrl(URL.createObjectURL(file));
  }

  function removePhoto() {
    URL.revokeObjectURL(photoUrl);
    setPhotoUrl("");
    setCutout(false);
    setPhoto(null);
  }

  async function suggest() {
    setCopyBusy(true);
    setError("");
    try {
      setCopies(await api.suggestCopies({ product_name: name.trim(), message: message.trim(), style, text_model: textModel }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCopyBusy(false);
    }
  }

  async function submit() {
    setTried(true);
    if (!ready) return;
    setBusy(true);
    setError("");
    try {
      if (detail) {
        const id = await api.startDetailPage(
          { product_name: name.trim(), message: message.trim(), features: features.map((f) => f.trim()).filter(Boolean), style, image_model: imageModel },
          photo,
        );
        router.push(`/detail/${id}`);
      } else {
        const g = await api.generate(
          { purpose, product_name: name.trim(), message: message.trim(), style, adjustments: [], parent_id: null, image_model: imageModel },
          photo,
        );
        saveCopies(g.id, copies);
        router.push(`/result/${g.id}`);
      }
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  if (busy)
    return detail ? (
      <Waiting title="상세페이지 만들기를 시작했어요" hint="곧 만드는 화면으로 넘어가요." />
    ) : (
      <Waiting title="이미지를 만들고 있어요" hint="보통 10~30초 걸려요. 이 화면을 닫지 말아 주세요." />
    );

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex flex-col gap-10"
    >
      <div>
        <Link href="/#start" className="-ml-2 inline-flex min-h-[44px] items-center gap-1 rounded-btn px-2 hint">
          <ChevronLeft aria-hidden className="size-5" /> 다른 곳 고르기
        </Link>
        <p className="mt-2 inline-block rounded-full bg-honey px-4 py-1 text-caption font-medium">{purposeTitle}</p>
        <h1 className="mt-3 text-h font-bold">무엇을 알리고 싶으세요?</h1>
      </div>

      {purpose === "commerce" && (
        <fieldset>
          <legend className="label">무엇을 만들까요?</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              { v: false, t: "대표 이미지 1장", d: "상품 목록에 보이는 사진" },
              { v: true, t: "상세페이지", d: "소개 5칸을 길게 이어 붙인 이미지 · 1분쯤 걸려요" },
            ].map((o) => (
              <button
                key={o.t}
                type="button"
                aria-pressed={detail === o.v}
                onClick={() => setDetail(o.v)}
                className={clsx("rounded-card border-2 p-5 text-left", detail === o.v ? "border-ink bg-pollen" : "border-mist bg-white")}
              >
                <span className="block font-semibold">{o.t}</span>
                <span className="hint">{o.d}</span>
              </button>
            ))}
          </div>
        </fieldset>
      )}

      <div>
        <label htmlFor="name" className="label">가게 또는 상품 이름</label>
        <input id="name" className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 동네꽃집, 수제 딸기잼" aria-invalid={tried && !name.trim()} aria-describedby="name-err" />
        {tried && !name.trim() && <FieldError id="name-err">이름을 적어 주세요.</FieldError>}
      </div>

      <div>
        <label htmlFor="msg" className="label">하고 싶은 말</label>
        <p className="mb-2 hint">이미지에 크게 들어갈 문장이에요. 짧을수록 잘 보여요.</p>
        <input id="msg" className="field" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="예: 주말 20% 할인, 신메뉴 출시" aria-invalid={tried && !message.trim()} aria-describedby="msg-err" />
        {tried && !message.trim() && <FieldError id="msg-err">하고 싶은 말을 적어 주세요.</FieldError>}

        <button type="button" onClick={suggest} disabled={!ready || copyBusy} className="btn-line mt-3 w-full sm:w-auto">
          <Sparkles aria-hidden className="size-5" />
          {copyBusy ? "문구를 생각하고 있어요…" : "더 좋은 문구 추천받기"}
        </button>
        {!ready && <p className="mt-2 hint">이름과 하고 싶은 말을 적으면 추천받을 수 있어요.</p>}
        {copies.length > 0 && (
          <div className="mt-4 flex flex-col gap-2" role="group" aria-label="추천 문구. 누르면 위 칸에 들어가요">
            {copies.map((c) => (
              <button key={c} type="button" onClick={() => setMessage(c)} aria-pressed={message === c} className={clsx("rounded-btn border-2 border-ink p-4 text-left", message === c ? "bg-ink text-white" : "bg-white hover:bg-mist")}>
                {c}
              </button>
            ))}
          </div>
        )}
      </div>

      {detail && (
        <fieldset>
          <legend className="label">상품의 좋은 점 (선택)</legend>
          <p className="mb-3 hint">비워 두면 알아서 채워 드려요.</p>
          <div className="flex flex-col gap-3">
            {features.map((f, i) => (
              <input key={i} className="field" aria-label={`좋은 점 ${i + 1}`} value={f} placeholder={["예: 무첨가", "예: 소량 생산", "예: 선물 포장"][i]} onChange={(e) => setFeatures(features.map((x, j) => (j === i ? e.target.value : x)))} />
            ))}
          </div>
        </fieldset>
      )}

      <fieldset>
        <legend className="label">원하는 느낌 (선택)</legend>
        <div className="flex flex-wrap gap-2">
          {STYLES.map((s) => (
            <Chip key={s} on={style === s} onClick={() => setStyle(style === s ? null : s)}>{s}</Chip>
          ))}
        </div>
      </fieldset>

      <div>
        <span className="label">상품 사진 (선택)</span>
        <p className="mb-3 hint">사진이 있으면 상품을 더 비슷하게 만들어요. PNG·JPG·WEBP, 10MB까지.</p>
        {photo && cutout ? (
          <CutoutEditor photoUrl={photoUrl} name={photo.name} onDone={pickPhoto} onCancel={() => setCutout(false)} />
        ) : photo ? (
          <div className="flex flex-col gap-3 rounded-btn bg-mist p-3">
            <div className="flex items-center gap-4">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={photoUrl} alt="올린 상품 사진" className="size-20 rounded-sm object-cover" />
              <span className="flex-1 truncate">{photo.name}</span>
              <button type="button" onClick={removePhoto} className="btn-line min-h-[44px] px-4" aria-label="사진 빼기">
                <X aria-hidden className="size-5" /> 빼기
              </button>
            </div>
            <button type="button" onClick={() => setCutout(true)} className="btn-line min-h-[44px]">
              <Scissors aria-hidden className="size-5" /> 배경 지우기
            </button>
          </div>
        ) : (
          <label className="flex min-h-[120px] cursor-pointer flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed border-charcoal hover:bg-mist">
            <ImagePlus aria-hidden className="size-8" />
            <span className="font-medium">사진 고르기</span>
            <input type="file" accept={PHOTO_TYPES.join(",")} className="sr-only" onChange={(e) => pickPhoto(e.target.files?.[0])} />
          </label>
        )}
        {photoError && <FieldError>{photoError}</FieldError>}
      </div>

      <details className="rounded-card border-2 border-mist p-5">
        <summary className="cursor-pointer font-semibold">품질 고르기 (선택)</summary>
        <div className="mt-5 flex flex-col gap-6">
          {[
            { legend: "그림", list: IMAGE_MODELS, value: imageModel as string, set: (v: string) => setImageModel(v as ImageModel) },
            { legend: "문구 추천", list: TEXT_MODELS, value: textModel as string, set: (v: string) => setTextModel(v as TextModel) },
          ].map((g) => (
            <fieldset key={g.legend}>
              <legend className="label">{g.legend}</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                {g.list.map((m) => (
                  <button key={m.id} type="button" aria-pressed={g.value === m.id} onClick={() => g.set(m.id)} className={clsx("rounded-card border-2 p-4 text-left", g.value === m.id ? "border-ink bg-pollen" : "border-mist bg-white")}>
                    <span className="block font-semibold">{m.title}</span>
                    <span className="hint">{m.desc}</span>
                  </button>
                ))}
              </div>
            </fieldset>
          ))}
        </div>
      </details>

      {error && <Notice>{error}</Notice>}

      <div className="sticky bottom-0 -mx-4 bg-white/95 px-4 py-4">
        <button type="submit" className="btn-fill w-full text-sub">
          {detail ? "상세페이지 만들기" : "이미지 만들기"}
        </button>
      </div>
    </form>
  );
}
