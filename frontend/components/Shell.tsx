import Link from "next/link";

export function Logo() {
  return (
    <Link href="/" className="inline-flex min-h-[44px] items-center gap-2 rounded-btn text-sub font-bold">
      <span aria-hidden className="grid size-6 place-items-center rounded-full bg-ink">
        <span className="size-2 rounded-full bg-honey" />
      </span>
      Just Make It
    </Link>
  );
}

/** 만들기 화면 공통 틀. 랜딩(/)은 자체 헤더를 씀 */
export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="mx-auto max-w-3xl px-4 py-3">
        <Logo />
      </header>
      <main className="mx-auto max-w-3xl px-4 pb-24">{children}</main>
    </>
  );
}
