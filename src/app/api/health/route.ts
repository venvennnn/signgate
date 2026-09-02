import { NextResponse } from "next/server";
import { foxitConfigured } from "@/lib/foxit";

export async function GET() {
  return NextResponse.json({
    ok: true,
    product: "SignGate",
    foxit_configured: foxitConfigured(),
  });
}
