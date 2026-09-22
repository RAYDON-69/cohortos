import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { listStyleProfiles, upsertStyleProfile, loadTokens } from "../../api/client"
import type { StyleProfile, ApiError } from "../../api/client"

/**
 * Style-lock / few-shot profile — Portion 20
 * Edit terminology, difficulty, sign conventions, few-shot examples.
 * Version increments on each upsert (service-side).
 */

export function StyleProfileScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [profiles, setProfiles] = useState<StyleProfile[]>([]);
  const [subject, setSubject] = useState("Physics");
  const [styleNotes, setStyleNotes] = useState("");
  const [terminology, setTerminology] = useState("");
  const [signs, setSigns] = useState("");
  const [difficulty, setDifficulty] = useState("medium");
  const [lang, setLang] = useState("en");
  const [fewShot, setFewShot] = useState("");
  const [version, setVersion] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listStyleProfiles(tenantId);
      setProfiles(res.profiles || []);
      const match = (res.profiles || []).find(
        (p) => (p.subject || "").toLowerCase() === subject.toLowerCase()
      );
      if (match) {
        setStyleNotes(match.style_notes || "");
        setTerminology((match.terminology || []).join(", "));
        setSigns(match.sign_conventions || "");
        setDifficulty(match.difficulty || "medium");
        setLang(match.preferred_language || "en");
        setVersion(match.version ?? null);
        const fs = match.few_shot_examples || [];
        setFewShot(
          fs.map((e) => `Q: ${e.input || ""}\nA: ${e.output || ""}`).join("\n\n")
        );
      } else {
        setVersion(null);
      }
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, subject, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function onSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const examples = fewShot
        .split(/\n\n+/)
        .map((block) => {
          const lines = block.trim().split("\n");
          const q = lines.find((l) => l.startsWith("Q:"))?.replace(/^Q:\s*/, "") || "";
          const a = lines.find((l) => l.startsWith("A:"))?.replace(/^A:\s*/, "") || "";
          return q || a ? { input: q, output: a } : null;
        })
        .filter(Boolean) as { input: string; output: string }[];
      const res = await upsertStyleProfile(tenantId, {
        subject: subject.trim(),
        style_notes: styleNotes,
        terminology: terminology
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        sign_conventions: signs,
        difficulty,
        preferred_language: lang,
        few_shot_examples: examples,
      });
      setVersion(res.profile.version ?? null);
      setSaved(true);
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  const nav = [
    { id: "review", label: t("navReview"), onClick: () => navigate("/teacher/review") },
    { id: "style", label: "Style profile", active: true },
    { id: "bank", label: "Item bank", onClick: () => navigate("/teacher/item-bank") },
    { id: "insight", label: "Cohort insight", onClick: () => navigate("/teacher/insight") },
    { id: "ocr", label: "OCR (beta)", onClick: () => navigate("/teacher/ocr") },
  ];

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Teacher · Style-lock profile">
      <h2 className="view-title">Style-lock / few-shot profile</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Terminology, difficulty, sign conventions, and few-shot examples. Each save bumps the
        version so generation stays locked to your centre&apos;s voice.
      </p>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}
      {saved && (
        <span className="badge badge-neutral-info" role="status">
          Saved · version {version ?? "—"}
        </span>
      )}

      {loading && <p className="caption muted">{t("loadingView")}</p>}

      <div className="style-layout">
        <Card>
          <div className="eyebrow">Subjects with profiles</div>
          <ul className="profile-list">
            {profiles.map((p) => (
              <li key={String(p.id || p.subject)}>
                <Button
                  size="sm"
                  variant={
                    (p.subject || "").toLowerCase() === subject.toLowerCase()
                      ? "primary"
                      : "outline"
                  }
                  onClick={() => setSubject(p.subject || "")}
                >
                  {p.subject} · v{p.version ?? 1}
                </Button>
              </li>
            ))}
            {profiles.length === 0 && (
              <li className="caption muted">No profiles yet — create one below.</li>
            )}
          </ul>
        </Card>

        <Card variant="featured">
          <FormField id="sp-subject" label="Subject" required>
            <TextInput
              id="sp-subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </FormField>
          <FormField id="sp-notes" label="Style notes">
            <textarea
              id="sp-notes"
              className="form-input"
              rows={3}
              value={styleNotes}
              onChange={(e) => setStyleNotes(e.target.value)}
            />
          </FormField>
          <FormField id="sp-terms" label="Terminology (comma-separated)">
            <TextInput
              id="sp-terms"
              value={terminology}
              onChange={(e) => setTerminology(e.target.value)}
            />
          </FormField>
          <FormField id="sp-signs" label="Sign conventions">
            <TextInput id="sp-signs" value={signs} onChange={(e) => setSigns(e.target.value)} />
          </FormField>
          <FormField id="sp-diff" label="Difficulty">
            <SelectInput
              id="sp-diff"
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value)}
            >
              <option value="easy">easy</option>
              <option value="medium">medium</option>
              <option value="hard">hard</option>
            </SelectInput>
          </FormField>
          <FormField id="sp-lang" label="Preferred language">
            <SelectInput id="sp-lang" value={lang} onChange={(e) => setLang(e.target.value)}>
              <option value="en">English</option>
              <option value="bn">Bangla</option>
              <option value="banglish">Banglish</option>
            </SelectInput>
          </FormField>
          <FormField
            id="sp-fs"
            label="Few-shot examples"
            hint="Blocks separated by a blank line. Use Q: and A: lines."
          >
            <textarea
              id="sp-fs"
              className="form-input"
              rows={6}
              value={fewShot}
              onChange={(e) => setFewShot(e.target.value)}
              spellCheck={false}
            />
          </FormField>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Button variant="primary" onClick={() => void onSave()} loading={saving}>
              Save profile
            </Button>
            {version != null && (
              <span className="caption mono-data">Current version {version}</span>
            )}
          </div>
        </Card>
      </div>

      <style>{`
        .style-layout {
          display: grid;
          grid-template-columns: minmax(180px, 0.6fr) minmax(280px, 1.4fr);
          gap: 20px;
        }
        @media (max-width: 760px) {
          .style-layout { grid-template-columns: 1fr; }
        }
        .profile-list {
          list-style: none;
          margin: 8px 0 0;
          padding: 0;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
      `}</style>
    </AppShell>
  );
}
