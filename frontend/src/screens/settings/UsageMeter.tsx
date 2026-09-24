/**
 * Settings → Usage — AI calls/cost this billing period (Phase 11).
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Card } from "../../components/Card";
import { Badge } from "../../components/Badge";
import { useLocale } from "../../i18n/LocaleContext";
import { loadTokens, billingUsage, billingSubscription } from "../../api/client";

type ProviderRow = {
  provider: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  estimated_cost_usd: number;
};

export function UsageMeterScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState("");
  const [totalCalls, setTotalCalls] = useState(0);
  const [totalCost, setTotalCost] = useState(0);
  const [rows, setRows] = useState<ProviderRow[]>([]);
  const [plan, setPlan] = useState("");
  const [included, setIncluded] = useState(0);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [subStatus, setSubStatus] = useState("");
  const [payProvider, setPayProvider] = useState("none");

  const nav = buildDeskNav(navigate, "settings", {
    attendance: t("navAttendance"),
    admissions: t("navAdmissions"),
    fees: t("navFees") || "Fees",
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const tid = loadTokens().tenant_id;
        if (!tid) throw new Error("Not signed in");
        const [u, s] = await Promise.all([billingUsage(tid), billingSubscription(tid)]);
        if (cancelled) return;
        setPeriod(u.period_key);
        setTotalCalls(u.total_calls);
        setTotalCost(u.total_estimated_cost_usd);
        setRows(u.by_provider || []);
        setPlan(u.plan_code || String(s.subscription?.plan_code || ""));
        setIncluded(u.ai_calls_included || 0);
        setRemaining(u.ai_calls_remaining ?? null);
        setSubStatus(u.subscription_status || String(s.subscription?.status || ""));
        setPayProvider(u.payment_provider || "none");
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load usage");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const pct =
    included > 0 ? Math.min(100, Math.round((totalCalls / included) * 100)) : totalCalls > 0 ? 100 : 0;

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Settings · Usage">
      <h2 className="view-title">Usage this period</h2>
      <p className="mb-4 text-sm text-slate-700">
        AI calls and estimated cost for the current billing month. Live payment is not connected yet —
        provider stays <strong>none</strong> until a rail is chosen.
      </p>

      {error && (
        <div className="mb-3 rounded-md bg-error-bg px-3 py-2 text-sm text-error" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <div className="grid max-w-2xl gap-4">
          <Card>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold text-ink">Period {period || "—"}</h3>
              <Badge variant="default">{plan || "starter"}</Badge>
              <Badge variant="ai-medium">{subStatus || "trial"}</Badge>
              <Badge variant="ai-low">pay: {payProvider}</Badge>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">AI calls</div>
                <div className="text-2xl font-semibold text-ink">{totalCalls}</div>
              </div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Included</div>
                <div className="text-2xl font-semibold text-ink">{included || "—"}</div>
              </div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Est. cost (USD)</div>
                <div className="text-2xl font-semibold text-ink">${totalCost.toFixed(4)}</div>
              </div>
            </div>
            {included > 0 && (
              <div className="mt-4">
                <div className="mb-1 flex justify-between text-xs text-slate-600">
                  <span>Allowance used</span>
                  <span>
                    {totalCalls} / {included}
                    {remaining != null ? ` (${remaining} left)` : ""}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-sage-100">
                  <div
                    className="h-full rounded-full bg-sage-700 transition-all"
                    style={{ width: `${pct}%` }}
                    role="progressbar"
                    aria-valuenow={pct}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  />
                </div>
              </div>
            )}
          </Card>

          <Card>
            <h3 className="mb-3 font-semibold text-ink">By provider</h3>
            {rows.length === 0 ? (
              <p className="text-sm text-slate-500">No AI calls recorded this period yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-border text-[11px] uppercase tracking-wide text-slate-500">
                      <th className="py-2 pr-2">Provider</th>
                      <th className="py-2 pr-2">Calls</th>
                      <th className="py-2 pr-2">Tokens in/out</th>
                      <th className="py-2">Est. USD</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.provider} className="border-b border-border last:border-0">
                        <td className="py-2 pr-2 font-medium">{r.provider}</td>
                        <td className="py-2 pr-2">{r.calls}</td>
                        <td className="py-2 pr-2 text-slate-600">
                          {r.tokens_in} / {r.tokens_out}
                        </td>
                        <td className="py-2">${Number(r.estimated_cost_usd).toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <p className="text-sm">
            <Link to="/settings" className="font-semibold text-sage-700 underline-offset-2 hover:underline">
              ← All settings
            </Link>
          </p>
        </div>
      )}
    </AppShell>
  );
}
