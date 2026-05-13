import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const INGEST_API_KEY = Deno.env.get("INGEST_API_KEY") ?? "";

/**
 * Accepts: { councils: [ { council: string, valid_refs: string[] } ] }
 * For each council, deletes any row in properties_large whose council_reference
 * is NOT in valid_refs. Used for one-time cleanup and nightly sync.
 */
Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  if (req.headers.get("x-api-key") !== INGEST_API_KEY) {
    return new Response("Unauthorized", { status: 401 });
  }

  let body: { councils: { council: string; valid_refs: string[] }[] };
  try {
    body = await req.json();
  } catch {
    return new Response("Bad Request", { status: 400 });
  }

  if (!Array.isArray(body.councils) || body.councils.length === 0) {
    return new Response(JSON.stringify({ deleted: 0 }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  let totalDeleted = 0;
  const errors: string[] = [];

  for (const { council, valid_refs } of body.councils) {
    if (!council) continue;

    try {
      let query = supabase
        .from("properties_large")
        .delete({ count: "exact" })
        .eq("county", council);

      if (valid_refs && valid_refs.length > 0) {
        query = query.not("council_reference", "in", `(${valid_refs.map(r => `"${r}"`).join(",")})`);
      }

      const { error, count } = await query;

      if (error) {
        console.error(`Error cleaning ${council}:`, error.message);
        errors.push(`${council}: ${error.message}`);
      } else {
        console.log(`Cleaned ${council}: deleted ${count ?? 0} orphans`);
        totalDeleted += count ?? 0;
      }
    } catch (err) {
      errors.push(`${council}: ${err}`);
    }
  }

  return new Response(
    JSON.stringify({ deleted: totalDeleted, errors }),
    { headers: { "Content-Type": "application/json" } },
  );
});
