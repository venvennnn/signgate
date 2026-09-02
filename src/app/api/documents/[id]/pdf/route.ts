import fs from "node:fs";
import { NextResponse } from "next/server";
import { pdfPath } from "@/lib/workflow";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const file = pdfPath(id);
    const buf = fs.readFileSync(file);
    return new NextResponse(new Uint8Array(buf), {
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `inline; filename="signgate-${id}.pdf"`,
      },
    });
  } catch {
    return NextResponse.json({ error: "No PDF" }, { status: 404 });
  }
}
