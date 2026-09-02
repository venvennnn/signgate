import { NextResponse } from "next/server";
import { createDocument, listDocuments } from "@/lib/workflow";

export async function GET() {
  return NextResponse.json({ documents: listDocuments() });
}

export async function POST(request: Request) {
  const body = (await request.json()) as { prompt?: string; actor?: string };
  if (!body.prompt?.trim()) {
    return NextResponse.json({ error: "prompt is required" }, { status: 400 });
  }
  const session = createDocument(body.prompt, body.actor);
  return NextResponse.json(session);
}
