"use client";

import { Button } from "@/components/ui/Button";
import { loadResult } from "@/lib/api";
import { Download, Link2, RefreshCw, Pencil } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const QUICK_EDITS = [
  "글자 더 크게",
  "더 밝게",
  "배경 단순하게",
  "텍스트 짧게",
];

export default function ResultPage() {
  const router = useRouter();
  const [data, setData] = useState<{
    imageUrl: string;
    source: string;
    productName: string;
    message: string;
    purpose: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const r = loadResult();
    if (!r) {
      router.replace("/");
      return;
    }
    setData(r);
  }, [router]);

  async function handleCopyLink() {
    if (!data?.imageUrl) return;
    try {
      await navigator.clipboard.writeText(data.imageUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  }

  function handleDownload() {
    if (!data?.imageUrl) return;
    const a = document.createElement("a");
    a.href = data.imageUrl;
    a.download = `just-make-it-${Date.now()}.png`;
    a.target = "_blank";
    a.rel = "noopener";
    a.click();
  }

  if (!data) {
    return (
      <div className="flex justify-center py-20 text-slate-500">불러오는 중…</div>
    );
  }

  return (
    <main>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          이미지가 준비됐어요
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          {data.purpose} · {data.productName}
        </p>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={data.imageUrl}
          alt={`${data.productName} 광고 이미지`}
          className="aspect-square w-full object-cover"
        />
        <div className="border-t border-slate-100 px-4 py-3 text-sm text-slate-500">
          “{data.message}”
          <span className="ml-2 text-xs text-slate-400">
            ({data.source === "openai" ? "프리미엄" : "기본"} 생성)
          </span>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3">
        <Button variant="primary" className="w-full" onClick={handleDownload}>
          <Download className="h-4 w-4" />
          다운로드
        </Button>
        <Button variant="outline" className="w-full" onClick={handleCopyLink}>
          <Link2 className="h-4 w-4" />
          {copied ? "복사됨!" : "링크 복사"}
        </Button>
      </div>

      <section className="mt-8">
        <h2 className="mb-3 flex items-center gap-1.5 text-sm font-medium text-slate-700">
          <Pencil className="h-4 w-4" />
          조금 수정하기
        </h2>
        <div className="flex flex-wrap gap-2">
          {QUICK_EDITS.map((label) => (
            <button
              key={label}
              type="button"
              className="rounded-full bg-slate-100 px-3.5 py-1.5 text-sm text-slate-700 hover:bg-slate-200"
              onClick={() => {
                // MVP: 수정 칩은 UI만. 이후 재생성 API에 옵션으로 전달
                alert(`“${label}” 옵션은 곧 연결됩니다.`);
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      <div className="mt-8 space-y-3">
        <Button
          variant="secondary"
          className="w-full"
          onClick={() => router.push("/create")}
        >
          <RefreshCw className="h-4 w-4" />
          같은 설정으로 다시 만들기
        </Button>
        <Button
          variant="ghost"
          className="w-full"
          onClick={() => router.push("/")}
        >
          처음부터 다시
        </Button>
      </div>
    </main>
  );
}
