import { PURPOSES, type Purpose } from "@/lib/types";
import { redirect } from "next/navigation";
import { CreateForm } from "./CreateForm";
import { Shell } from "@/components/Shell";

export default async function CreatePage({ searchParams }: { searchParams: Promise<{ purpose?: string }> }) {
  const { purpose } = await searchParams;
  const found = PURPOSES.find((p) => p.id === purpose);
  if (!found) redirect("/#start");
  return (
    <Shell>
      <CreateForm purpose={found.id as Purpose} purposeTitle={found.title} />
    </Shell>
  );
}
