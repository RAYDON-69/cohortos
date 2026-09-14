import { useLocale } from "../i18n/LocaleContext";
import "./LanguageToggle.css";

/**
 * Language toggle §4.11 — EN / বাংলা.
 * Must not reload or lose form state.
 */

export function LanguageToggle({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useLocale();

  return (
    <div className={`lang-toggle ${className}`} role="group" aria-label={t("language")}>
      <button
        type="button"
        className={`lang-btn ${locale === "en" ? "active" : ""}`}
        onClick={() => setLocale("en")}
        aria-pressed={locale === "en"}
      >
        {t("langEn")}
      </button>
      <button
        type="button"
        className={`lang-btn ${locale === "bn" ? "active" : ""}`}
        onClick={() => setLocale("bn")}
        aria-pressed={locale === "bn"}
      >
        {t("langBn")}
      </button>
    </div>
  );
}
