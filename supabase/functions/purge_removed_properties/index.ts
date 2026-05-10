import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const INGEST_API_KEY = Deno.env.get("INGEST_API_KEY") ?? "";

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  if (req.headers.get("x-api-key") !== INGEST_API_KEY) {
    return new Response("Unauthorized", { status: 401 });
  }

  let body: { council: string; ds_refs: string[] };
  try {
    body = await req.json();
  } catch {
    return new Response("Bad Request", { status: 400 });
  }

  const { council, ds_refs } = body;
  if (!council || !Array.isArray(ds_refs) || ds_refs.length === 0) {
    return new Response(JSON.stringify({ deleted: 0 }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const { error, count } = await supabase
    .from("properties_large")
    .delete({ count: "exact" })
    .eq("county", council)
    .in("council_reference", ds_refs);

  if (error) {
    console.error("purge_removed_properties error:", error.message);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  console.log(`Deleted ${count} properties for ${council}`);
  return new Response(JSON.stringify({ deleted: count ?? 0 }), {
    headers: { "Content-Type": "application/json" },
  });
});
