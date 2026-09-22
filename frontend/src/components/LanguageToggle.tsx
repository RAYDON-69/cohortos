import { useLocale } from "../i18n/LocaleContext";
import { Button } from "./ui/button";

export function LanguageToggle() {
  const { locale, setLocale } = useLocale();
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => setLocale(locale === "en" ? "bn" : "en")}
      aria-label="Toggle language"
    >
      {locale === "en" ? "বাংলা" : "EN"}
    </Button>
  );
}
