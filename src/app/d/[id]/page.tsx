import { Workspace } from "@/components/Workspace";
import { getSession } from "@/lib/workflow";
import { notFound } from "next/navigation";

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const session = getSession(id);
    return <Workspace initial={session} />;
  } catch {
    notFound();
  }
}
