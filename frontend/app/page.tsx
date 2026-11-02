import { SampleCard } from "@/components/SampleCard";
import { SAMPLES } from "@/lib/samples";
import { Logo } from "@/components/Shell";
import { PURPOSES } from "@/lib/types";
import { ArrowRight, Check, ChevronRight, MousePointerClick, PencilLine, Sparkles } from "lucide-react";
import Link from "next/link";

const TILT = ["-rotate-6", "rotate-3", "-rotate-2", "rotate-6"];
const STRIP = [...PURPOSES.map((p) => p.title), "쿠팡 상세페이지"];
const STEPS = [
  { icon: MousePointerClick, t: "어디에 쓸지 고르기", d: "인스타그램, 스마트스토어, 유튜브, 카카오톡 중에서 골라요. 크기와 비율은 알아서 맞춰요." },
  { icon: PencilLine, t: "가게 이름과 하고 싶은 말 적기", d: "'소금빵', '신메뉴 출시'처럼 짧게 적어도 충분해요. 문구가 막막하면 추천받으세요." },
  { icon: Check, t: "완성, 바로 저장", d: "글자는 그 자리에서 고치고, 그림이 마음에 안 들면 '더 밝게'처럼 골라 다시 만들어요." },
];

export default function Home() {
  return (
    <>
      <div className="bg-honey">
        <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Logo />
          <Link href="#start" className="btn-fill min-h-[44px] px-4 text-caption">
            광고 만들기 <ArrowRight aria-hidden className="size-4" />
          </Link>
        </header>

        <section className="mx-auto max-w-6xl px-4 pb-14 pt-6">
          <p className="mx-auto mb-4 flex w-fit items-center gap-1.5 rounded-full bg-white px-4 py-1.5 text-caption font-medium">
            <Sparkles aria-hidden className="size-4" /> 소상공인을 위한 AI 광고 스튜디오
          </p>
          <p aria-hidden className="text-center text-[15vw] font-bold leading-none tracking-[0.02em] sm:text-[128px]">
            Just Make It.
          </p>
          <ul className="mx-auto -mt-2 grid max-w-4xl grid-cols-2 gap-4 sm:-mt-10 sm:grid-cols-4" aria-label="만든 광고 예시">
            {SAMPLES.map((s, i) => (
              <li key={s.src} className={`${TILT[i]} transition-transform hover:rotate-0`}>
                <SampleCard i={i} />
              </li>
            ))}
          </ul>
          <div className="mt-12 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h1 className="text-h font-bold sm:text-h-lg">
                디자이너 없이,
                <br />
                오늘 올릴 광고를 지금.
              </h1>
              <p className="mt-3 max-w-xl">가게 이름과 하고 싶은 말만 적어 주세요. 올릴 곳에 맞는 크기로 바로 만들어 드려요.</p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Link href="#start" className="btn-fill">
                무료로 광고 만들기 <ArrowRight aria-hidden className="size-5" />
              </Link>
              <Link href="#how" className="btn bg-white hover:bg-mist">어떻게 만드나요?</Link>
            </div>
          </div>
        </section>
      </div>

      <div className="overflow-hidden bg-ink py-4 text-white" aria-hidden>
        <div className="flex w-max animate-marquee gap-10 whitespace-nowrap font-medium">
          {[...STRIP, ...STRIP].map((t, i) => (
            <span key={i} className="flex items-center gap-10">
              {t} <span className="size-2 rounded-full bg-honey" />
            </span>
          ))}
        </div>
      </div>

      <main>
        <section id="start" className="mx-auto max-w-3xl scroll-mt-4 px-4 py-16">
          <h2 className="text-h font-bold">어디에 올릴 이미지인가요?</h2>
          <p className="mb-8 mt-2 hint">고르면 그곳에 맞는 크기로 만들어 드려요.</p>
          <ul className="grid gap-4 sm:grid-cols-2">
            {PURPOSES.map((p) => (
              <li key={p.id}>
                <Link href={`/create?purpose=${p.id}`} className="card flex min-h-[96px] items-center gap-4 transition-colors hover:bg-mist">
                  <span className="flex-1">
                    <span className="block text-sub font-semibold">{p.title}</span>
                    <span className="hint">{p.desc}</span>
                  </span>
                  <ChevronRight aria-hidden className="size-6 shrink-0" />
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <section id="how" className="bg-mist py-16">
          <div className="mx-auto max-w-6xl px-4">
            <h2 className="text-h font-bold">광고 한 장, 세 단계면 끝나요</h2>
            <p className="mt-2 hint">어려운 디자인 프로그램도, 따로 공부할 것도 없어요.</p>
            <ol className="mt-8 grid gap-4 sm:grid-cols-3">
              {STEPS.map(({ icon: Icon, t, d }, i) => (
                <li key={t} className="card">
                  <span className="flex items-center justify-between">
                    <span className="grid size-11 place-items-center rounded-full bg-honey">
                      <Icon aria-hidden className="size-5" />
                    </span>
                    <span aria-hidden className="text-h font-bold text-graphite/40">0{i + 1}</span>
                  </span>
                  <h3 className="mt-5 text-sub font-semibold">{t}</h3>
                  <p className="mt-2 text-caption text-graphite">{d}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-16">
          <h2 className="text-h font-bold">분위기 하나만 골라도 이렇게 달라져요</h2>
          <p className="mt-2 hint">밝고 경쾌한, 고급스러운, 따뜻한, 심플한, 강렬한 중에서 가게에 어울리는 걸 골라 보세요.</p>
          <ul className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {SAMPLES.map((s, i) => (
              <li key={s.src}>
                <SampleCard i={i} />
                <p className="mt-3 w-fit rounded-full bg-honey px-3 py-0.5 text-caption font-medium">{s.style}</p>
                <p className="mt-1 text-caption text-graphite">{s.note}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="bg-honey px-4 py-20 text-center">
          <p aria-hidden className="text-[15vw] font-bold leading-none tracking-[0.02em] sm:text-[112px]">Just Make It.</p>
          <p className="mt-4">고민은 짧게, 광고는 지금. 첫 광고를 만들어 보세요.</p>
          <Link href="#start" className="btn-fill mt-6">
            무료로 광고 만들기 <ArrowRight aria-hidden className="size-5" />
          </Link>
        </section>
      </main>

      <footer className="mx-auto max-w-6xl px-4 py-10">
        <Logo />
        <p className="mt-2 text-caption text-graphite">소상공인의 광고를 쉽게. 스프린트 AI 12기 4팀 프로젝트.</p>
      </footer>
    </>
  );
}
