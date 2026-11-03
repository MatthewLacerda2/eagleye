import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { EventTypeRead } from "@/lib/schemas/cameras";
import type { Review, ReviewWrite } from "@/lib/schemas/observations";

interface ReviewControlsProps {
  events: string[];
  review: Review | null;
  eventTypes: EventTypeRead[];
  onSubmit: (review: ReviewWrite) => void;
  pending?: boolean;
}

function toggle(list: string[], key: string, on: boolean): string[] {
  return on ? [...list, key] : list.filter((k) => k !== key);
}

/** Correct in one click; Incorrect asks which events were wrong or missed. */
export function ReviewControls({
  events,
  review,
  eventTypes,
  onSubmit,
  pending = false,
}: ReviewControlsProps) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [wrong, setWrong] = useState<string[]>([]);
  const [missed, setMissed] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const names = new Map(eventTypes.map((e) => [e.key, e.name]));

  if (editing) {
    return (
      <div className="flex flex-col gap-3">
        {events.map((key) => (
          <div key={`w-${key}`} className="flex items-center gap-2">
            <Checkbox
              id={`wrong-${key}`}
              onCheckedChange={(v) => setWrong(toggle(wrong, key, v === true))}
            />
            <Label htmlFor={`wrong-${key}`}>
              {t("review.wrong", { name: names.get(key) ?? key })}
            </Label>
          </div>
        ))}
        {eventTypes
          .filter((e) => !events.includes(e.key))
          .map((e) => (
            <div key={`m-${e.key}`} className="flex items-center gap-2">
              <Checkbox
                id={`missed-${e.key}`}
                onCheckedChange={(v) =>
                  setMissed(toggle(missed, e.key, v === true))
                }
              />
              <Label htmlFor={`missed-${e.key}`}>
                {t("review.missed", { name: e.name })}
              </Label>
            </div>
          ))}
        <Textarea
          value={note}
          onChange={(ev) => setNote(ev.target.value)}
          placeholder={t("review.notePlaceholder")}
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={pending}
            onClick={() => {
              onSubmit({
                review: "incorrect",
                wrong_events: wrong,
                missed_events: missed,
                note: note.trim() || null,
              });
              setEditing(false);
            }}
          >
            {t("review.save")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
            {t("review.cancel")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {review && (
        <Badge variant={review === "correct" ? "secondary" : "destructive"}>
          {t(`review.state.${review}`)}
        </Badge>
      )}
      <Button
        size="sm"
        variant="outline"
        disabled={pending}
        onClick={() =>
          onSubmit({
            review: "correct",
            wrong_events: [],
            missed_events: [],
            note: null,
          })
        }
      >
        {t("review.correct")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={pending}
        onClick={() => setEditing(true)}
      >
        {t("review.incorrect")}
      </Button>
    </div>
  );
}
