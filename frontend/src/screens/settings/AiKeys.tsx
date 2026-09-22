import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { apiRequest, loadTokens, tenantPath } from "../../api/client";

export function AiKeysScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tenantId = loadTokens().tenant_id || "";
  const [provider, setProvider] = useState("groq");
  const [apiKey, setApiKey] = useState("");
  const [configured, setConfigured] = useState(false);
  const [masked, setMasked] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [question, setQuestion] = useState("How many students do we have?");
  const [answer, setAnswer] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const r = await apiRequest<{ configured: boolean; masked_key?: string; provider?: string }>(
          tenantPath(tenantId, "/settings/ai-keys")
        );
        setConfigured(!!r.configured);
        setMasked(r.masked_key || null);
        if (r.provider) setProvider(r.provider);
      } catch {
        /* ignore */
      }
    })();
  }, [tenantId]);

  const nav = buildDeskNav(navigate, "settings", {
    attendance: t("navAttendance"),
    admissions: t("navAdmissions"),
    fees: t("navFees") || "Fees",
  });

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Settings · AI keys">
      <h2 className="view-title">AI API keys</h2>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        Use your own Groq, NVIDIA NIM, OpenAI, or Claude key. Keys stay on this centre only — never committed to git.
      </p>
      <Card>
        <FormField id="prov" label="Provider">
          <SelectInput id="prov" value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="groq">Groq (developer key)</option>
            <option value="nim">NVIDIA NIM (API key)</option>
            <option value="openai">OpenAI Platform key</option>
            <option value="anthropic">Anthropic Console key</option>
            <option value="gemini">Google AI Studio (Gemini) key</option>
            <option value="deepseek">DeepSeek (api.deepseek.com) — default cheap tier</option>
          </SelectInput>
        <p className="caption muted">
          Bring your own API key from the provider&apos;s developer console — not a ChatGPT Plus / Claude Pro login.
          Links: platform.openai.com · console.anthropic.com · aistudio.google.com · console.groq.com · platform.deepseek.com
        </p>
        </FormField>
        <FormField id="key" label="API key">
          <TextInput
            id="key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={masked || "sk-…"}
          />
        </FormField>
        <p className="caption muted">{configured ? `Saved key on file: ${masked}` : "No key saved yet."}</p>
        <Button
          variant="primary"
          onClick={async () => {
            await apiRequest(tenantPath(tenantId, "/settings/ai-keys"), {
              method: "PUT",
              body: { provider, api_key: apiKey },
            });
            setMsg("Key saved");
            setConfigured(true);
          }}
          disabled={!apiKey.trim()}
        >
          Save key
        </Button>
        {msg && <p className="caption">{msg}</p>}
      </Card>
      <Card>
        <h3 className="card-title">Ask about this centre</h3>
        <FormField id="q" label="Question">
          <TextInput id="q" value={question} onChange={(e) => setQuestion(e.target.value)} />
        </FormField>
        <Button
          variant="outline"
          onClick={async () => {
            const r = await apiRequest<{ answer: string }>(tenantPath(tenantId, "/ai/query"), {
              method: "POST",
              body: { question },
            });
            setAnswer(r.answer);
          }}
        >
          Ask
        </Button>
        {answer && <p style={{ marginTop: 12 }}>{answer}</p>}
      </Card>
    </AppShell>
  );
}
