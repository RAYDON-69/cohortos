import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MobileShell } from "../../shell/MobileShell";
import { LanguageToggle } from "../../components/LanguageToggle";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { getParentPortal, getParentStudentSummary, getParentNotifications, getParentPreferences, setParentPreference, createStudentAccount, loadTokens } from "../../api/client"
import type { ParentChild, ParentNotification, NotifPref, ApiError } from "../../api/client"
import "../../components/FormField.css";
import "../../components/LanguageToggle.css";
import "../../shell/MobileShell.css";

/**
 * Parent portal — Portion 22
 * Multi-student switcher with unambiguous centre context.
 * Notifications are filtered per selected student (no cross-child blast).
 */

const PARENT_KEY = "cohortos_parent_account_id";

const EVENT_LABELS: Record<string, string> = {
  attendance_absent: "Absence alerts",
  payment_due: "Fee due",
  exam_result: "Exam results",
  ai_flagged: "Teacher review flags",
};

export function ParentPortalScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [parentId, setParentId] = useState(
    () => localStorage.getItem(PARENT_KEY) || ""
  );
  const [centreName, setCentreName] = useState("");
  const [children, setChildren] = useState<ParentChild[]>([]);
  const [selectedStudentId, setSelectedStudentId] = useState<string>("");
  const [summary, setSummary] = useState<{
    student?: { name?: string; roll?: string };
    attendance?: { status?: string; date?: string }[];
    payments?: { status?: string; year?: number; month?: number }[];
    results?: { chapter_or_topic?: string; percentage?: number; is_absent?: boolean; exam_date?: string }[];
  } | null>(null);
  const [notifications, setNotifications] = useState<ParentNotification[]>([]);
  const [prefs, setPrefs] = useState<NotifPref[]>([]);
  const [eventTypes, setEventTypes] = useState<string[]>([]);
  const [channels, setChannels] = useState<string[]>(["sms", "whatsapp"]);
  const [prefEvent, setPrefEvent] = useState("attendance_absent");
  const [prefChannel, setPrefChannel] = useState("sms");
  const [prefEnabled, setPrefEnabled] = useState(true);
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedPref, setSavedPref] = useState(false);

  const loadPortal = useCallback(async (pid: string) => {
    if (!pid) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getParentPortal(tenantId, pid);
      setCentreName(res.centre_name || tenantId);
      setChildren(res.children || []);
      const first = res.children?.[0]?.student_id || "";
      setSelectedStudentId((prev) => prev || first);
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, t]);

  useEffect(() => {
    if (parentId) void loadPortal(parentId);
  }, [parentId, loadPortal]);

  useEffect(() => {
    if (!parentId || !selectedStudentId) {
      setSummary(null);
      setNotifications([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [sum, notif] = await Promise.all([
          getParentStudentSummary(tenantId, parentId, selectedStudentId),
          getParentNotifications(tenantId, parentId, selectedStudentId),
        ]);
        if (cancelled) return;
        setSummary(sum);
        setNotifications(notif.notifications || []);
      } catch (e) {
        if (!cancelled) setError((e as ApiError).detail || t("genericError"));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [parentId, selectedStudentId, tenantId, t]);

  useEffect(() => {
    if (!parentId) return;
    getParentPreferences(tenantId, parentId)
      .then((r) => {
        setPrefs(r.preferences || []);
        setEventTypes(r.event_types || Object.keys(EVENT_LABELS));
        setChannels(r.channels || ["sms", "whatsapp", "push", "email"]);
      })
      .catch(() => {
        /* optional */
      });
  }, [parentId, tenantId]);

  async function onBootstrapParent() {
    setLoading(true);
    setError(null);
    try {
      // Reuse account create with parent role
      const res = await createStudentAccount(tenantId, {
        role: "parent",
        phone: phone || "01900000000",
        display_name: "Parent",
      });
      const id = res.account.id;
      localStorage.setItem(PARENT_KEY, id);
      setParentId(id);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setLoading(false);
    }
  }

  async function onSavePref() {
    if (!parentId || !selectedStudentId) return;
    setSavedPref(false);
    try {
      await setParentPreference(tenantId, parentId, {
        user_id: parentId,
        student_id: selectedStudentId,
        channel_type: prefChannel,
        event_type: prefEvent,
        enabled: prefEnabled,
      });
      setSavedPref(true);
      const r = await getParentPreferences(tenantId, parentId);
      setPrefs(r.preferences || []);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    }
  }

  const selectedChild = children.find((c) => c.student_id === selectedStudentId);
  const studentName =
    selectedChild?.student?.name || summary?.student?.name || selectedStudentId || "—";
  const studentRoll = selectedChild?.student?.roll || summary?.student?.roll;

  const tabs = [
    { id: "parent", label: "Parent", active: true },
    { id: "student", label: t("navHome"), onClick: () => navigate("/student") },
  ];

  return (
    <MobileShell
      centreName={centreName || t("appName")}
      tabs={tabs}
      languageSlot={<LanguageToggle />}
    >
      {/* Centre isolation banner — UI trust requirement */}
      <div className="centre-banner" role="status">
        <span className="centre-eyebrow">Centre in view</span>
        <strong>{centreName || tenantId}</strong>
        <span className="caption">
          Data below is only for this centre. Switching centres requires signing into that
          centre&apos;s account.
        </span>
      </div>

      <h1 className="view-title" style={{ fontSize: 22 }}>
        Parent portal
      </h1>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}

      {!parentId && (
        <Card variant="featured">
          <div className="eyebrow">Start parent session (demo)</div>
          <FormField id="p-phone" label="Phone">
            <TextInput id="p-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </FormField>
          <Button variant="primary" onClick={() => void onBootstrapParent()} loading={loading}>
            Create parent account
          </Button>
          <p className="caption" style={{ marginTop: 8 }}>
            Staff link students to this parent via the admissions desk.
          </p>
        </Card>
      )}

      {parentId && (
        <>
          {/* Multi-student switcher — only students of THIS centre */}
          <Card>
            <div className="eyebrow">Linked students · {centreName || "this centre"}</div>
            {children.length === 0 && (
              <p className="caption muted">
                No linked students in this centre yet. Ask the desk to link an admission.
              </p>
            )}
            <div className="child-switcher" role="listbox" aria-label="Linked students">
              {children.map((ch) => {
                const active = ch.student_id === selectedStudentId;
                return (
                  <button
                    key={ch.student_id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    className={`child-chip ${active ? "active" : ""}`}
                    onClick={() => setSelectedStudentId(ch.student_id)}
                  >
                    <span className="child-name">{ch.student?.name || "Student"}</span>
                    <span className="mono-data caption">
                      Roll {ch.student?.roll || "—"}
                    </span>
                  </button>
                );
              })}
            </div>
          </Card>

          {selectedStudentId && (
            <div className="parent-stack">
              <Card variant="insight">
                <div className="eyebrow">Viewing</div>
                <div style={{ fontSize: 18, fontWeight: 600 }}>{studentName}</div>
                {studentRoll && (
                  <span className="caption mono-data">Roll {studentRoll}</span>
                )}
                <span className="badge badge-neutral-info" role="status" style={{ marginTop: 8 }}>
                  {centreName}
                </span>
              </Card>

              <Card>
                <div className="eyebrow">Attendance (recent)</div>
                <ul className="mini-list">
                  {(summary?.attendance || []).slice(-5).reverse().map((a, i) => (
                    <li key={i}>
                      <span className="mono-data">{a.date || "—"}</span>
                      <span
                        className={`badge badge-attendance-${a.status || "absent"}`}
                        role="status"
                      >
                        {a.status || "—"}
                      </span>
                    </li>
                  ))}
                  {!(summary?.attendance || []).length && (
                    <li className="caption muted">No records</li>
                  )}
                </ul>
              </Card>

              <Card>
                <div className="eyebrow">Fees</div>
                <ul className="mini-list">
                  {(summary?.payments || []).slice(-4).map((p, i) => (
                    <li key={i}>
                      <span className="mono-data">
                        {p.year}-{String(p.month).padStart(2, "0")}
                      </span>
                      <span
                        className={
                          p.status === "paid" || p.status === "locked"
                            ? "badge badge-payment-locked"
                            : "badge badge-payment-due"
                        }
                        role="status"
                      >
                        {p.status || "—"}
                      </span>
                    </li>
                  ))}
                  {!(summary?.payments || []).length && (
                    <li className="caption muted">No records</li>
                  )}
                </ul>
              </Card>

              <Card>
                <div className="eyebrow">Results</div>
                <ul className="mini-list">
                  {(summary?.results || []).slice(0, 5).map((r, i) => (
                    <li key={i}>
                      <span>{r.chapter_or_topic || r.exam_date || "Exam"}</span>
                      <span className="mono-data">
                        {r.is_absent ? "Absent" : `${r.percentage ?? "—"}%`}
                      </span>
                    </li>
                  ))}
                  {!(summary?.results || []).length && (
                    <li className="caption muted">No results</li>
                  )}
                </ul>
              </Card>

              {/* Per-student notifications — never a multi-child blast */}
              <Card>
                <div className="eyebrow">
                  Updates for {studentName}
                  <span className="caption" style={{ display: "block", fontWeight: 400 }}>
                    Filtered to this student only
                  </span>
                </div>
                <ul className="mini-list">
                  {notifications.map((n, i) => (
                    <li key={String(n.id || i)}>
                      <span>
                        {n.subject || n.event_type || "Update"}
                        <span className="caption" style={{ display: "block" }}>
                          {(n.content || "").slice(0, 80)}
                        </span>
                      </span>
                      <span className="mono-data caption">
                        {(n.created_at || "").slice(0, 10)}
                      </span>
                    </li>
                  ))}
                  {notifications.length === 0 && (
                    <li className="caption muted">No updates for this student yet.</li>
                  )}
                </ul>
              </Card>

              <Card variant="featured">
                <div className="eyebrow">Notification preferences · per student</div>
                <p className="caption" style={{ marginBottom: 12 }}>
                  Preferences are stored for the selected student. Turning on absence alerts
                  for one child does not enable them for siblings.
                </p>
                <FormField id="pe" label="Event">
                  <SelectInput
                    id="pe"
                    value={prefEvent}
                    onChange={(e) => setPrefEvent(e.target.value)}
                  >
                    {(eventTypes.length ? eventTypes : Object.keys(EVENT_LABELS)).map((et) => (
                      <option key={et} value={et}>
                        {EVENT_LABELS[et] || et}
                      </option>
                    ))}
                  </SelectInput>
                </FormField>
                <FormField id="pc" label="Channel">
                  <SelectInput
                    id="pc"
                    value={prefChannel}
                    onChange={(e) => setPrefChannel(e.target.value)}
                  >
                    {channels.map((ch) => (
                      <option key={ch} value={ch}>
                        {ch}
                      </option>
                    ))}
                  </SelectInput>
                </FormField>
                <label className="channel-row" style={{ marginBottom: 12 }}>
                  <input
                    type="checkbox"
                    checked={prefEnabled}
                    onChange={(e) => setPrefEnabled(e.target.checked)}
                  />
                  <span>Enabled for {studentName}</span>
                </label>
                <Button variant="primary" onClick={() => void onSavePref()}>
                  Save preference
                </Button>
                {savedPref && (
                  <span className="badge badge-neutral-info" role="status" style={{ marginLeft: 8 }}>
                    Saved for this student
                  </span>
                )}
                {prefs.length > 0 && (
                  <ul className="mini-list" style={{ marginTop: 16 }}>
                    {prefs.map((pr, i) => (
                      <li key={i}>
                        <span className="caption">
                          {pr.event_type} · {pr.channel_type}
                        </span>
                        <span className="badge badge-neutral-info" role="status">
                          {pr.enabled ? "on" : "off"}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          )}
        </>
      )}

      <style>{`
        .centre-banner {
          background: var(--peri-bg);
          border: 1px solid var(--peri-300);
          border-radius: 12px;
          padding: 12px 14px;
          margin-bottom: 16px;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .centre-eyebrow {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          color: var(--peri-text);
        }
        .child-switcher {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 10px;
        }
        .child-chip {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          gap: 2px;
          border: 1px solid var(--border);
          background: var(--white);
          border-radius: 12px;
          padding: 10px 14px;
          font: inherit;
          cursor: pointer;
          min-height: 44px;
          min-width: 120px;
        }
        .child-chip.active {
          border-color: var(--sage-700);
          background: var(--sage-100);
        }
        .child-name { font-weight: 600; font-size: 14px; }
        .parent-stack { display: grid; gap: 14px; margin-top: 14px; }
        .mini-list {
          list-style: none;
          margin: 8px 0 0;
          padding: 0;
        }
        .mini-list li {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 10px;
          padding: 8px 0;
          border-bottom: 1px solid var(--border);
          font-size: 14px;
        }
        .channel-row {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
        }
      `}</style>
    </MobileShell>
  );
}
