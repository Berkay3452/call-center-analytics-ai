import { createCall, createCallWithAudio, isMockEnabled } from "@/lib/api/client";

export async function POST(request: Request) {
  if (!isMockEnabled()) return new Response(null, { status: 404 });
  const result = request.headers.get("content-type")?.includes("multipart/form-data")
    ? await createCallWithAudio(await request.formData())
    : await createCall(await request.json());
  return Response.json(result, { status: 202, headers: { "Cache-Control": "no-store" } });
}
