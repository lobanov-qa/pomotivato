/**
 * Screen placeholder for routes whose real component lands in a later PR
 * (spec 03 §10 chain). All copy comes from the dictionary (spec 03 §7).
 */

import { t, type MessageKey } from "../i18n/ru";

export default function Placeholder({ titleKey }: { titleKey: MessageKey }) {
  return (
    <section className="py-16 text-center" data-testid="placeholder.root">
      <h1 className="text-2xl font-semibold">{t(titleKey)}</h1>
      <p className="mt-2 text-muted-foreground">{t("app.placeholder.body")}</p>
    </section>
  );
}
