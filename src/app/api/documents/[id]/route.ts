import { NextResponse } from "next/server";
import { getSession, updateDraftManifest } from "@/lib/workflow";
import type { IntentManifest } from "@/lib/types";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    return NextResponse.json(getSession(id));
  } catch {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json()) as { manifest: IntentManifest; actor?: string };
  try {
    return NextResponse.json(updateDraftManifest(id, body.manifest, body.actor));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Failed" }, { status: 400 });
  }
}
