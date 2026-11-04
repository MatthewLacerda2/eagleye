import { useState } from "react";
import { Link, createFileRoute } from "@tanstack/react-router";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FrameImage } from "@/components/frame-image";
import { ReviewControls } from "@/components/review-controls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listCameras, listEventTypes } from "@/lib/api/cameras";
import {
  PAGE_SIZE,
  listObservations,
  observationFramePath,
  reviewObservation,
} from "@/lib/api/observations";
import { formatDateTime } from "@/lib/format";
import type { ReviewWrite } from "@/lib/schemas/observations";

const ALL = "all";
const POLL_MS = 30_000;

function ObservationsPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [onlyEvents, setOnlyEvents] = useState(true);
  const [unreviewed, setUnreviewed] = useState(false);
  const [site, setSite] = useState(ALL);
  const [event, setEvent] = useState(ALL);
  const filters = {
    only_events: onlyEvents,
    unreviewed,
    site: site === ALL ? null : site,
    event: event === ALL ? null : event,
  };

  const eventTypes = useQuery({
    queryKey: ["catalog"],
    queryFn: listEventTypes,
  });
  const cameras = useQuery({ queryKey: ["cameras"], queryFn: listCameras });
  const sites = [
    ...new Map((cameras.data ?? []).map((c) => [c.site_key, c.site_name])),
  ];
  const names = new Map((eventTypes.data ?? []).map((e) => [e.key, e.name]));

  const pages = useInfiniteQuery({
    queryKey: ["observations", filters],
    queryFn: ({ pageParam }) =>
      listObservations({ ...filters, before: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) =>
      last.length === PAGE_SIZE ? last[last.length - 1].observed_at : undefined,
    refetchInterval: POLL_MS,
  });
  const rows = pages.data?.pages.flat() ?? [];

  const review = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ReviewWrite }) =>
      reviewObservation(id, payload),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["observations"] }),
  });

  return (
    <section className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-h1">{t("observations.heading")}</h1>
        <p className="text-body text-muted-foreground">
          {t("observations.subheading")}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <Checkbox
            id="only-events"
            checked={onlyEvents}
            onCheckedChange={(v) => setOnlyEvents(v === true)}
          />
          <Label htmlFor="only-events">{t("observations.onlyEvents")}</Label>
        </div>
        <div className="flex items-center gap-2">
          <Checkbox
            id="unreviewed"
            checked={unreviewed}
            onCheckedChange={(v) => setUnreviewed(v === true)}
          />
          <Label htmlFor="unreviewed">{t("observations.unreviewed")}</Label>
        </div>
        <Select value={site} onValueChange={setSite}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t("observations.allSites")}</SelectItem>
            {sites.map(([key, name]) => (
              <SelectItem key={key} value={key}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={event} onValueChange={setEvent}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t("observations.allEvents")}</SelectItem>
            {(eventTypes.data ?? []).map((e) => (
              <SelectItem key={e.key} value={e.key}>
                {e.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {pages.isLoading ? (
        <p className="text-body text-muted-foreground">
          {t("observations.loading")}
        </p>
      ) : pages.isError ? (
        <p className="text-body text-destructive">{t("observations.error")}</p>
      ) : rows.length === 0 ? (
        <p className="text-body text-muted-foreground">
          {t("observations.empty")}
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("observations.columns.frame")}</TableHead>
              <TableHead>{t("observations.columns.when")}</TableHead>
              <TableHead>{t("observations.columns.where")}</TableHead>
              <TableHead>{t("observations.columns.events")}</TableHead>
              <TableHead>{t("observations.columns.description")}</TableHead>
              <TableHead>{t("observations.columns.review")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((o) => (
              <TableRow key={o.id}>
                <TableCell>
                  <Link to="/observations/$id" params={{ id: o.id }}>
                    <FrameImage
                      path={observationFramePath(o.id)}
                      alt={t("frame.alt", { camera: o.camera_label })}
                      className="h-20 w-32"
                    />
                  </Link>
                </TableCell>
                <TableCell className="text-caption">
                  {formatDateTime(o.observed_at, i18n.language)}
                </TableCell>
                <TableCell>
                  <div className="text-body">{o.site_name}</div>
                  <div className="text-caption text-muted-foreground">
                    {o.camera_label}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {o.events.length === 0 ? (
                      <span className="text-caption text-muted-foreground">
                        {t("observations.noEvents")}
                      </span>
                    ) : (
                      o.events.map((k) => (
                        <Badge key={k} variant="destructive">
                          {names.get(k) ?? k}
                        </Badge>
                      ))
                    )}
                  </div>
                </TableCell>
                <TableCell className="max-w-64 text-body whitespace-normal">
                  {o.description}
                </TableCell>
                <TableCell>
                  <ReviewControls
                    events={o.events}
                    review={o.review}
                    eventTypes={eventTypes.data ?? []}
                    pending={review.isPending}
                    onSubmit={(payload) => review.mutate({ id: o.id, payload })}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {pages.hasNextPage && (
        <Button
          variant="outline"
          className="self-center"
          disabled={pages.isFetchingNextPage}
          onClick={() => void pages.fetchNextPage()}
        >
          {t("observations.loadMore")}
        </Button>
      )}
    </section>
  );
}

export const Route = createFileRoute("/_authenticated/")({
  component: ObservationsPage,
});
