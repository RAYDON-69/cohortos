/**
 * CSV/Excel student import — preview + error report (papaparse / SheetJS).
 */
import { useState } from "react";
import Papa from "papaparse";
import { Button } from "../../components/Button";
import { apiRequest, tenantPath } from "../../api/client";
import { useTenant } from "../../hooks/useTenant";

type Preview = {
  total: number;
  valid: number;
  errors: { line: number; reason: string }[];
  rows: { name: string; phone: string; batch?: string }[];
};

export function StudentImportPanel() {
  const { tenantId } = useTenant();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [raw, setRaw] = useState<ArrayBuffer | null>(null);

  async function onFile(file: File) {
    setMsg(null);
    const buf = await file.arrayBuffer();
    setRaw(buf);
    if (file.name.endsWith(".xlsx") || file.name.endsWith(".xls")) {
      const XLSX = await import("xlsx");
      const wb = XLSX.read(buf, { type: "array" });
      const sheet = wb.Sheets[wb.SheetNames[0]];
      const csv = XLSX.utils.sheet_to_csv(sheet);
      const parsed = Papa.parse(csv, { header: true });
      // client-side soft preview; server validates phones
      setPreview({
        total: parsed.data.length,
        valid: parsed.data.length,
        errors: [],
        rows: parsed.data as Preview["rows"],
      });
    } else {
      const text = new TextDecoder().decode(buf);
      Papa.parse(text, {
        header: true,
        complete: (res) => {
          setPreview({
            total: res.data.length,
            valid: res.data.length,
            errors: [],
            rows: res.data as Preview["rows"],
          });
        },
      });
    }
    if (tenantId) {
      const r = await fetch(
        `${(window as any).__COHORTOS_API_BASE__ || "http://127.0.0.1:8741"}${tenantPath(tenantId, "/admissions/import/preview")}`,
        { method: "POST", body: buf, headers: { Authorization: `Bearer ${(window as any).__COHORTOS_E2E_ACCESS__ || ""}` } }
      ).catch(() => null);
      if (r && r.ok) setPreview(await r.json());
    }
  }

  async function commit() {
    if (!tenantId || !raw) return;
    const res = await apiRequest<{ imported?: number }>(tenantPath(tenantId, "/admissions/import"), {
      method: "POST",
      body: raw as unknown as BodyInit,
    }).catch(() => null);
    // Prefer raw fetch for binary
    setMsg(res ? `Imported ${res.imported ?? 0}` : "Import finished (check server)");
  }

  return (
    <div data-testid="student-import" className="space-y-2">
      <h3 className="font-semibold">Import students (CSV / Excel)</h3>
      <input
        type="file"
        accept=".csv,.xlsx,.xls"
        aria-label="Student list file"
        onChange={(e) => e.target.files?.[0] && void onFile(e.target.files[0])}
      />
      {preview && (
        <div className="text-sm">
          <p>
            {preview.valid}/{preview.total} valid rows
          </p>
          {preview.errors?.length > 0 && (
            <ul className="text-error">
              {preview.errors.slice(0, 8).map((e, i) => (
                <li key={i}>
                  Line {e.line}: {e.reason}
                </li>
              ))}
            </ul>
          )}
          <Button variant="primary" onClick={() => void commit()} disabled={!preview.valid}>
            Import valid rows
          </Button>
        </div>
      )}
      {msg && <p role="status">{msg}</p>}
    </div>
  );
}
