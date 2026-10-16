"use client";

import { PurposeSelector } from "@/components/PurposeSelector";
import { Button } from "@/components/ui/Button";
import { saveDraft } from "@/lib/api";
import type { Purpose } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function HomePage() {
  const router = useRouter();
  const [purpose, setPurpose] = useState<Purpose | undefined>();

  function handleNext() {
    if (!purpose) return;
    saveDraft({ purpose });
    router.push("/create");
  }

  return (
    <main>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          어디에 쓸 이미지인가요?
        </h1>
        <p className="mt-2 text-slate-600">
          용도에 맞는 비율과 스타일로 바로 만들어 드려요.
        </p>
      </div>

      <PurposeSelector value={purpose} onChange={setPurpose} />

      <div className="mt-8">
        <Button
          className="w-full"
          size="lg"
          disabled={!purpose}
          onClick={handleNext}
        >
          다음
        </Button>
      </div>
    </main>
  );
}
