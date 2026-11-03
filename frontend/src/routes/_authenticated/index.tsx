import { createFileRoute } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

function ObservationsPage() {
  const { t } = useTranslation();

  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-h1">{t("observations.heading")}</h1>
        <p className="text-body text-muted-foreground">
          {t("observations.subheading")}
        </p>
      </div>
    </section>
  );
}

export const Route = createFileRoute("/_authenticated/")({
  component: ObservationsPage,
});
