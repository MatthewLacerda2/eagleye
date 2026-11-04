import { Link, createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FrameImage } from "@/components/frame-image";
import { ReviewControls } from "@/components/review-controls";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listEventTypes } from "@/lib/api/cameras";
import {
  getObservation,
  observationFramePath,
  reviewObservation,
} from "@/lib/api/observations";
import { formatDateTime } from "@/lib/format";
import type { ReviewWrite } from "@/lib/schemas/observations";

function ObservationDetailPage() {
  const { id } = Route.useParams();
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ["observation", id],
    queryFn: () => getObservation(id),
  });
  const eventTypes = useQuery({
    queryKey: ["catalog"],
    queryFn: listEventTypes,
  });
  const names = new Map((eventTypes.data ?? []).map((e) => [e.key, e.name]));
  const review = useMutation({
    mutationFn: (payload: ReviewWrite) => reviewObservation(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["observation", id] });
      void queryClient.invalidateQueries({ queryKey: ["observations"] });
    },
  });

  if (detail.isLoading) {
    return (
      <p className="text-body text-muted-foreground">{t("detail.loading")}</p>
    );
  }
  if (detail.isError || !detail.data) {
    return <p className="text-body text-destructive">{t("detail.error")}</p>;
  }
  const o = detail.data;
  const a = o.analysis;

  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-6">
      <Link to="/" className="text-body text-primary">
        {t("detail.back")}
      </Link>
      <div className="flex flex-col gap-1">
        <h1 className="text-h2">
          {o.site_name} · {o.camera_label}
        </h1>
        <p className="text-body text-muted-foreground">
          {formatDateTime(o.observed_at, i18n.language)}
        </p>
      </div>
      <FrameImage
        path={observationFramePath(o.id)}
        alt={t("frame.alt", { camera: o.camera_label })}
        className="aspect-video w-full"
      />
      <div className="flex flex-wrap gap-2">
        {o.events.map((k) => (
          <Badge key={k} variant="destructive">
            {names.get(k) ?? k}
          </Badge>
        ))}
      </div>
      <p className="text-body">{o.description}</p>
      <ReviewControls
        events={o.events}
        review={o.review}
        eventTypes={eventTypes.data ?? []}
        pending={review.isPending}
        onSubmit={(payload) => review.mutate(payload)}
      />
      <Card>
        <CardHeader>
          <CardTitle>{t("detail.analysis")}</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-2 text-body">
          <span className="text-muted-foreground">{t("detail.model")}</span>
          <span>{a.model}</span>
          <span className="text-muted-foreground">{t("detail.status")}</span>
          <span>{a.status}</span>
          <span className="text-muted-foreground">{t("detail.latency")}</span>
          <span>{t("detail.ms", { value: a.latency_ms })}</span>
          <span className="text-muted-foreground">{t("detail.tokens")}</span>
          <span>
            {a.input_tokens} · {a.cache_read_tokens} · {a.cache_write_tokens} ·{" "}
            {a.output_tokens}
          </span>
          <span className="text-muted-foreground">{t("detail.cost")}</span>
          <span>{t("detail.usd", { value: a.cost_usd.toFixed(5) })}</span>
        </CardContent>
      </Card>
      {o.siblings.length > 0 && (
        <div className="flex flex-col gap-3">
          <h2 className="text-h3">{t("detail.siblings")}</h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
            {o.siblings.map((s) => (
              <Link key={s.id} to="/observations/$id" params={{ id: s.id }}>
                <FrameImage
                  path={observationFramePath(s.id)}
                  alt={t("frame.alt", { camera: s.camera_label })}
                  className="aspect-video w-full"
                />
                <p className="text-caption text-muted-foreground">
                  {s.camera_label} · {s.description}
                </p>
              </Link>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export const Route = createFileRoute("/_authenticated/observations/$id")({
  component: ObservationDetailPage,
});
