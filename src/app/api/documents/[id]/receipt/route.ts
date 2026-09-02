import { NextResponse } from "next/server";
import { buildReceipt } from "@/lib/workflow";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const url = new URL(request.url);
  const format = url.searchParams.get("format") ?? "json";
  try {
    const receipt = await buildReceipt(id);
    if (format === "pdf") {
      return new NextResponse(new Uint8Array(receipt.pdf), {
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": `attachment; filename="signgate-receipt-${id}.pdf"`,
        },
      });
    }
    return NextResponse.json(receipt.json);
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Failed" }, { status: 400 });
  }
}
