import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FrameImage } from "@/components/frame-image";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cameraFramePath, listCameras } from "@/lib/api/cameras";
import { formatDateTime } from "@/lib/format";
import type { CameraStatus } from "@/lib/schemas/cameras";

const POLL_MS = 30_000;

function bySite(cameras: CameraStatus[]): [string, CameraStatus[]][] {
  const groups = new Map<string, CameraStatus[]>();
  for (const camera of cameras) {
    groups.set(camera.site_name, [
      ...(groups.get(camera.site_name) ?? []),
      camera,
    ]);
  }
  return [...groups];
}

function CamerasPage() {
  const { t, i18n } = useTranslation();
  const cameras = useQuery({
    queryKey: ["cameras"],
    queryFn: listCameras,
    refetchInterval: POLL_MS,
  });

  return (
    <section className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-h1">{t("cameras.heading")}</h1>
        <p className="text-body text-muted-foreground">
          {t("cameras.subheading")}
        </p>
      </div>
      {cameras.isLoading ? (
        <p className="text-body text-muted-foreground">
          {t("cameras.loading")}
        </p>
      ) : cameras.isError ? (
        <p className="text-body text-destructive">{t("cameras.error")}</p>
      ) : (
        bySite(cameras.data ?? []).map(([site, list]) => (
          <div key={site} className="flex flex-col gap-3">
            <h2 className="text-h3">{site}</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {list.map((c) => (
                <Card key={c.id}>
                  <CardHeader className="flex flex-row items-center justify-between">
                    <CardTitle>{c.label}</CardTitle>
                    <Badge
                      variant={
                        c.status === "offline" ? "destructive" : "secondary"
                      }
                    >
                      {c.enabled
                        ? t(`cameras.status.${c.status}`)
                        : t("cameras.disabled")}
                    </Badge>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2">
                    {c.has_frame && (
                      <FrameImage
                        path={cameraFramePath(c.id)}
                        alt={t("frame.alt", { camera: c.label })}
                        className="aspect-video w-full"
                      />
                    )}
                    <p className="text-caption text-muted-foreground">
                      {t("cameras.lastCapture")}:{" "}
                      {formatDateTime(c.last_capture_at, i18n.language)}
                    </p>
                    <p className="text-caption text-muted-foreground">
                      {t("cameras.lastSent")}:{" "}
                      {formatDateTime(c.last_sent_at, i18n.language)}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        ))
      )}
    </section>
  );
}

export const Route = createFileRoute("/_authenticated/cameras")({
  component: CamerasPage,
});
