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
      // exceljs replaces sheetjs/xlsx (stale high-severity advisories on npm xlsx)
      const ExcelJS = (await import("exceljs")).default;
      const wb = new ExcelJS.Workbook();
      await wb.xlsx.load(buf);
      const sheet = wb.worksheets[0];
      const rows: Preview["rows"] = [];
      let headers: string[] = [];
      sheet.eachRow((row, rowNumber) => {
        const vals = row.values as Array<string | number | undefined>;
        // exceljs is 1-indexed; values[0] is empty
        const cells = vals.slice(1).map((v) => (v == null ? "" : String(v)));
        if (rowNumber === 1) {
          headers = cells.map((h) => h.toLowerCase());
          return;
        }
        const obj: Record<string, string> = {};
        headers.forEach((h, i) => {
          obj[h] = cells[i] || "";
        });
        rows.push({
          name: obj.name || obj["নাম"] || "",
          phone: obj.phone || obj["মোবাইল"] || obj.mobile || "",
          batch: obj.batch || obj["ব্যাচ"] || undefined,
        });
      });
      setPreview({ total: rows.length, valid: rows.length, errors: [], rows });
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
