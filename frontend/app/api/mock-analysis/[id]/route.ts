import { getCallById, isMockEnabled } from "@/lib/api/client";
import { readMockAnalysis, startMockAnalysis } from "@/lib/api/mock-analysis";

type Context = { params: Promise<{ id: string }> };

export async function GET(request: Request, { params }: Context) {
  if (!isMockEnabled()) return new Response(null, { status: 404 });
  const { id } = await params;
  const result = new URL(request.url).searchParams.has("detail") ? await getCallById(id) : readMockAnalysis(id);
  return Response.json(result, { headers: { "Cache-Control": "no-store" } });
}

export async function POST(_request: Request, { params }: Context) {
  if (!isMockEnabled()) return new Response(null, { status: 404 });
  const { id } = await params;
  return Response.json(startMockAnalysis(id), { status: 202, headers: { "Cache-Control": "no-store" } });
}
