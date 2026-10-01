/** Mobile one-tap join — Bangla-first labels. */
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

export function StudentJoinScreen() {
  const { tenantId, sessionId } = useParams();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [meta, setMeta] = useState<{
    title_bn?: string;
    button_bn?: string;
    join_url?: string;
    access_mode?: string;
    access_mode_warning?: string;
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!tenantId || !sessionId || !token) {
      setErr("লিংক অবৈধ — টোকেন নেই");
      return;
    }
    const base = (window as any).__COHORTOS_API_BASE__ || "";
    fetch(`${base}/join/${tenantId}/${sessionId}?token=${encodeURIComponent(token)}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json();
      })
      .then(setMeta)
      .catch((e) => setErr(String(e)));
  }, [tenantId, sessionId, token]);

  return (
    <div style={{ padding: 24, fontFamily: "system-ui", maxWidth: 420, margin: "0 auto" }} data-testid="student-join">
      <h1>{meta?.title_bn || "ক্লাসে যোগ দিন"}</h1>
      {err && <p role="alert">{err}</p>}
      {meta?.access_mode === "OPEN-ROOM" && (
        <p style={{ color: "#b45309" }}>সতর্কতা: পাবলিক রুম — JWT নিয়ন্ত্রিত নয়।</p>
      )}
      {meta?.join_url && (
        <a
          href={meta.join_url}
          style={{
            display: "block",
            textAlign: "center",
            padding: 16,
            background: "#0f766e",
            color: "#fff",
            borderRadius: 12,
            textDecoration: "none",
            fontSize: 18,
          }}
        >
          {meta.button_bn || "এক ট্যাপে যোগ দিন"}
        </a>
      )}
    </div>
  );
}
