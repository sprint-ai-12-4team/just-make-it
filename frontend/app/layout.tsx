import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Just Make It — 광고 이미지 만들기",
  description:
    "소상공인을 위한 AI 광고 이미지 생성. 인스타, 스마트스토어, 유튜브 썸네일을 쉽게 만드세요.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>
        <div className="mx-auto min-h-screen max-w-lg px-4 pb-16 pt-6 sm:max-w-xl sm:pt-10">
          <header className="mb-8 flex items-center justify-between">
            <a href="/" className="text-lg font-bold tracking-tight text-slate-900">
              Just Make It
            </a>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-500">
              베타
            </span>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
