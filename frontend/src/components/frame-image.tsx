import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchFrameUrl } from "@/lib/api/frames";
import { cn } from "@/lib/utils";

interface FrameImageProps {
  path: string;
  alt: string;
  className?: string;
}

/** A stored camera frame, loaded with the session's token; a placeholder if missing. */
export function FrameImage({ path, alt, className }: FrameImageProps) {
  const { t } = useTranslation();
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchFrameUrl(path).then(
      (created) => {
        objectUrl = created;
        if (cancelled) URL.revokeObjectURL(created);
        else setUrl(created);
      },
      () => {
        if (!cancelled) setFailed(true);
      },
    );
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (url) {
    return (
      <img
        src={url}
        alt={alt}
        className={cn("rounded-md object-cover", className)}
      />
    );
  }
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-md bg-muted text-caption text-muted-foreground",
        className,
      )}
    >
      {failed ? t("frame.missing") : t("frame.loading")}
    </div>
  );
}
