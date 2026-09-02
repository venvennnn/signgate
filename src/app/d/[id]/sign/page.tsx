import { SignDesk } from "@/components/SignDesk";
import { getSession } from "@/lib/workflow";
import { notFound, redirect } from "next/navigation";

export default async function SignPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const session = getSession(id);
    if (!session.signature_request) {
      redirect(`/d/${id}`);
    }
    return (
      <SignDesk
        id={id}
        title={session.document.title}
        signer={session.approved_manifest?.payload.signer.name ?? "Authorized signer"}
        status={session.signature_request.status}
      />
    );
  } catch {
    notFound();
  }
}
