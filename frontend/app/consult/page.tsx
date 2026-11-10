import { Shell } from "@/components/Shell";
import { PURPOSES, type Purpose } from "@/lib/types";
import { ConsultChat } from "./ConsultChat";

export default async function ConsultPage({ searchParams }: { searchParams: Promise<{ id?: string; purpose?: string; name?: string }> }) {
  const { id, purpose, name } = await searchParams;
  const p = PURPOSES.find((x) => x.id === purpose)?.id as Purpose | undefined;
  return (
    <Shell>
      <ConsultChat initialId={id} purpose={p} productName={name} />
    </Shell>
  );
}
