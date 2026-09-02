import { NextResponse } from "next/server";
import {
  approveManifest,
  completeHumanSignature,
  generateDocument,
  introduceAdversary,
  requestSignature,
  restoreApproved,
  verifyCurrent,
} from "@/lib/workflow";

type Action =
  | "approve"
  | "generate"
  | "verify"
  | "adversary"
  | "restore"
  | "esign"
  | "human_sign";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json()) as { action: Action; actor?: string; notes?: string; signer_email?: string };
  try {
    switch (body.action) {
      case "approve":
        return NextResponse.json(approveManifest(id, body.actor, body.notes));
      case "generate":
        return NextResponse.json(await generateDocument(id, body.actor));
      case "verify":
        return NextResponse.json(await verifyCurrent(id, body.actor));
      case "adversary":
        return NextResponse.json(await introduceAdversary(id, body.actor));
      case "restore":
        return NextResponse.json(await restoreApproved(id, body.actor));
      case "esign":
        return NextResponse.json(await requestSignature(id, body.actor, body.signer_email));
      case "human_sign":
        return NextResponse.json(completeHumanSignature(id, body.actor ?? "human:signer"));
      default:
        return NextResponse.json({ error: "Unknown action" }, { status: 400 });
    }
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Failed" }, { status: 400 });
  }
}
