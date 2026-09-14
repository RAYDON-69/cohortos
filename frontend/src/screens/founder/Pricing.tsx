import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { founderPricingTiers, founderQuote } from "../../api/client"
import type { ApiError } from "../../api/client"
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * Pricing / tier management — Portion 23
 * Quote tool over PricingEngine.calculate. Tier table is read from engine limits.
 */

export function PricingScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const [tiers, setTiers] = useState<
    { id: string; limit: number; base_price_bdt: number }[]
  >([]);
  const [count, setCount] = useState("200");
  const [tier, setTier] = useState("");
  const [cycle, setCycle] = useState("monthly");
  const [quote, setQuote] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [quoting, setQuoting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await founderPricingTiers();
      setTiers(res.tiers || []);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  async function onQuote() {
    setQuoting(true);
    setError(null);
    try {
      const res = await founderQuote({
        student_count: Number(count) || 0,
        tier: tier || undefined,
        billing_cycle: cycle,
      });
      setQuote(res.quote);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setQuoting(false);
    }
  }

  const nav = [
    { id: "dash", label: "Dashboard", onClick: () => navigate("/founder") },
    { id: "provision", label: "Provision", onClick: () => navigate("/founder/provision") },
    { id: "pricing", label: "Pricing", active: true },
  ];

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Founder · Pricing">
      <h2 className="view-title">Pricing & tiers</h2>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        Tier limits and base prices from the pricing engine. Quotes support monthly and annual
        cycles.
      </p>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}
      {loading && <p className="caption muted">{t("loadingView")}</p>}

      <div className="price-grid">
        {tiers.map((tr) => (
          <Card key={tr.id}>
            <div className="eyebrow">{tr.id}</div>
            <div className="kpi-value mono-data">৳{tr.base_price_bdt.toLocaleString()}</div>
            <p className="caption">Up to {tr.limit.toLocaleString()} students / month</p>
          </Card>
        ))}
      </div>

      <Card variant="featured" style={{ marginTop: 20 } as React.CSSProperties}>
        <div className="eyebrow">Quote</div>
        <FormField id="q-n" label="Student count">
          <TextInput
            id="q-n"
            type="number"
            value={count}
            onChange={(e) => setCount(e.target.value)}
          />
        </FormField>
        <FormField id="q-tier" label="Tier override">
          <SelectInput id="q-tier" value={tier} onChange={(e) => setTier(e.target.value)}>
            <option value="">Auto</option>
            <option value="starter">starter</option>
            <option value="growth">growth</option>
            <option value="scale">scale</option>
          </SelectInput>
        </FormField>
        <FormField id="q-cycle" label="Billing cycle">
          <SelectInput id="q-cycle" value={cycle} onChange={(e) => setCycle(e.target.value)}>
            <option value="monthly">monthly</option>
            <option value="annual">annual</option>
          </SelectInput>
        </FormField>
        <Button variant="primary" onClick={() => void onQuote()} loading={quoting}>
          Calculate quote
        </Button>

        {quote && (
          <dl className="quote-dl">
            {Object.entries(quote).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd className="mono-data">{String(v)}</dd>
              </div>
            ))}
          </dl>
        )}
      </Card>

      <style>{`
        .price-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 12px;
        }
        .kpi-value {
          font-size: 24px;
          font-weight: 700;
        }
        .quote-dl {
          margin-top: 16px;
        }
        .quote-dl > div {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 12px;
          padding: 6px 0;
          border-bottom: 1px solid var(--border);
          font-size: 14px;
        }
        .quote-dl dt { color: var(--slate-700); }
        .quote-dl dd { margin: 0; }
      `}</style>
    </AppShell>
  );
}
