import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { ocrAssist, loadTokens } from "../../api/client"
import type { ApiError } from "../../api/client"
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * OCR grading assist — Portion 20
 * Backend is a stub. Entry is labeled optional/beta.
 * Never pretends a grade exists when the service returns not implemented.
 */

export function OcrAssistScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [imageRef, setImageRef] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    ok: boolean;
    message?: string;
    transcription?: string | null;
    grade?: unknown;
    conceptual_flags?: unknown[];
  } | null>(null);
  const [implemented, setImplemented] = useState<boolean | null>(null);

  async function onRun() {
    if (!imageRef.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await ocrAssist(tenantId, imageRef.trim());
      setResult(res.result);
      setImplemented(res.implemented);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setLoading(false);
    }
  }

  const nav = [
    { id: "review", label: t("navReview"), onClick: () => navigate("/teacher/review") },
    { id: "bank", label: "Item bank", onClick: () => navigate("/teacher/item-bank") },
    { id: "ocr", label: "OCR (beta)", active: true },
  ];

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Teacher · OCR assist (beta)">
      <h2 className="view-title">OCR grading assist</h2>

      <div className="beta-banner" role="status">
        <strong>Optional / beta</strong>
        <span>
          Handwriting OCR is a stub in the current backend. Results will not invent a grade or
          transcription — if the service is not implemented, that is shown honestly and the item
          still needs teacher review.
        </span>
      </div>

      <p className="caption muted" style={{ marginBottom: 16 }}>
        Intended flow: upload handwritten answer → transcription side-by-side with image →
        rubric-flagged errors. Until the OCR provider is wired, this screen only demonstrates the
        gate.
      </p>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}

      <Card>
        <FormField
          id="ocr-ref"
          label="Image reference"
          hint="Path or URL the service will use (stub accepts any string)"
          required
        >
          <TextInput
            id="ocr-ref"
            value={imageRef}
            onChange={(e) => setImageRef(e.target.value)}
            placeholder="e.g. uploads/script-12.jpg"
          />
        </FormField>
        <Button
          variant="primary"
          onClick={() => void onRun()}
          loading={loading}
          disabled={!imageRef.trim()}
        >
          Run OCR assist
        </Button>
      </Card>

      {result && (
        <Card variant="queue-flagged" style={{ marginTop: 20 } as React.CSSProperties}>
          <div className="eyebrow">Service response</div>
          {implemented === false && (
            <div className="warning-banner" role="status" style={{ marginBottom: 12 }}>
              Not implemented — needs teacher review. No transcription or grade was produced.
            </div>
          )}
          <dl className="ocr-dl">
            <div>
              <dt>ok</dt>
              <dd className="mono-data">{String(result.ok)}</dd>
            </div>
            <div>
              <dt>message</dt>
              <dd>{result.message || "—"}</dd>
            </div>
            <div>
              <dt>transcription</dt>
              <dd>{result.transcription ?? "— (none)"}</dd>
            </div>
            <div>
              <dt>grade</dt>
              <dd>{result.grade == null ? "— (none)" : String(result.grade)}</dd>
            </div>
          </dl>
          <p className="caption" style={{ marginTop: 12 }}>
            Teacher action remains required. Do not treat this panel as an auto-grade.
          </p>
        </Card>
      )}

      <style>{`
        .beta-banner {
          display: flex;
          flex-direction: column;
          gap: 6px;
          background: var(--peri-bg);
          border: 1px solid var(--peri-300);
          border-radius: 12px;
          padding: 14px 16px;
          margin-bottom: 16px;
          font-size: 14px;
          color: var(--ink);
        }
        .beta-banner strong {
          text-transform: uppercase;
          letter-spacing: 0.04em;
          font-size: 12px;
          color: var(--peri-text);
        }
        .ocr-dl {
          display: grid;
          gap: 10px;
          margin: 0;
        }
        .ocr-dl div {
          display: grid;
          grid-template-columns: 120px 1fr;
          gap: 8px;
          font-size: 14px;
        }
        .ocr-dl dt {
          font-weight: 600;
          color: var(--slate-700);
        }
        .ocr-dl dd {
          margin: 0;
        }
      `}</style>
    </AppShell>
  );
}
