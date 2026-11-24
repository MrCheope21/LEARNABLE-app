import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Schemas } from "../../api/client";
import { learningItems } from "../../api/endpoints";
import { AuthImage } from "../../components/AuthImage";
import { useReadOnlyCourse } from "../../components/CourseAccess";
import { DrawingPad, dataUrlToBlob } from "../../components/DrawingPad";
import { ErrorBanner } from "../../components/QueryState";
import { useI18n } from "../../i18n";

type Item = Schemas["LearningItemRead"];

/**
 * "Answer by drawing": the reference drawing that is this question's answer (a molecule, a
 * diagram, a graph). Uploaded as an image, or drawn here. Students then answer by drawing.
 */
export function ReferenceDrawingEditor({ item, onChanged }: { item: Item; onChanged: () => void }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [sketching, setSketching] = useState(false);
  const [sketch, setSketch] = useState<string | null>(null);
  const done = () => {
    void queryClient.invalidateQueries({ queryKey: ["reference-drawing", item.id] });
    setSketching(false);
    setSketch(null);
    onChanged();
  };
  const upload = useMutation({ mutationFn: (file: Blob) => learningItems.setReferenceDrawing(item.id, file), onSuccess: done });
  const remove = useMutation({ mutationFn: () => learningItems.removeReferenceDrawing(item.id), onSuccess: done });
  const busy = upload.isPending || remove.isPending;
  const drawn = item.answer_format === "DRAWING";
  const readOnly = useReadOnlyCourse();

  if (readOnly) {
    // A course from the marketplace: the author's drawing, to look at.
    return drawn ? (
      <section className="reference-drawing" aria-label={t("drawing.answerBy")}>
        <h4>{t("drawing.answerBy")}</h4>
        <p className="hint">{t("drawing.youDraw")}</p>
        <AuthImage queryKey={["reference-drawing", item.id]} load={() => learningItems.referenceDrawing(item.id)} alt={t("drawing.referenceAlt")} className="drawing-image" />
      </section>
    ) : null;
  }

  return (
    <section className="reference-drawing" aria-label={t("drawing.answerBy")}>
      <h4>{t("drawing.answerBy")}</h4>
      {drawn ? (
        <>
          <p className="hint">{t("drawing.studentsDraw")}</p>
          <AuthImage queryKey={["reference-drawing", item.id]} load={() => learningItems.referenceDrawing(item.id)} alt={t("drawing.referenceAlt")} className="drawing-image" />
        </>
      ) : (
        <p className="hint">{t("drawing.explain")}</p>
      )}
      {sketching ? (
        <>
          <DrawingPad onChange={setSketch} disabled={busy} />
          <div className="actions" style={{ marginTop: 0 }}>
            <button type="button" className="primary" disabled={!sketch || busy} onClick={() => sketch && upload.mutate(dataUrlToBlob(sketch))}>
              {t("drawing.save")}
            </button>
            <button type="button" className="link" onClick={() => setSketching(false)}>
              {t("common.cancel")}
            </button>
          </div>
        </>
      ) : (
        <div className="actions" style={{ marginTop: 0 }}>
          <label className="button">
            {drawn ? t("drawing.replace") : t("drawing.upload")}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              hidden
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) upload.mutate(file);
                e.target.value = "";
              }}
            />
          </label>
          <button type="button" disabled={busy} onClick={() => setSketching(true)}>
            {drawn ? t("drawing.drawNew") : t("drawing.drawHere")}
          </button>
          {drawn && (
            <button type="button" className="link danger" disabled={busy} onClick={() => remove.mutate()}>
              {t("drawing.words")}
            </button>
          )}
        </div>
      )}
      <ErrorBanner error={upload.error ?? remove.error} />
    </section>
  );
}
