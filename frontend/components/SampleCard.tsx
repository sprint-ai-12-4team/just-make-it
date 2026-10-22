"use client";

import { SAMPLES } from "@/lib/samples";
import { AdPreview } from "./AdPreview";

export function SampleCard({ i }: { i: number }) {
  const s = SAMPLES[i];
  return <AdPreview width={768} layout={{ pos: "bottom", big: false }} panels={[{ src: s.src, title: s.title, sub: s.sub }]} />;
}
