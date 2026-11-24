import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Schemas } from "../../api/client";
import { learningItems } from "../../api/endpoints";
import { AuthImage } from "../../components/AuthImage";
import { ErrorBanner } from "../../components/QueryState";
import { useI18n } from "../../i18n";

type Item = Schemas["LearningItemRead"];

/** A picture shown with the question: a graph, a table or a diagram the student has to read. */
export function QuestionImageEditor({ item, onChanged }: { item: Item; onChanged: () => void }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const done = () => {
    void queryClient.invalidateQueries({ queryKey: ["question-image", item.id] });
    onChanged();
  };
  const upload = useMutation({ mutationFn: (file: Blob) => learningItems.setQuestionImage(item.id, file), onSuccess: done });
  const remove = useMutation({ mutationFn: () => learningItems.removeQuestionImage(item.id), onSuccess: done });
  const busy = upload.isPending || remove.isPending;
  const has = Boolean(item.question_image_type);

  return (
    <section className="reference-drawing" aria-label={t("qimage.title")}>
      <h4>{t("qimage.title")}</h4>
      {has ? (
        <AuthImage queryKey={["question-image", item.id]} load={() => learningItems.questionImage(item.id)} alt={t("qimage.alt")} className="question-image" />
      ) : (
        <p className="hint">{t("qimage.hint")}</p>
      )}
      <div className="actions" style={{ marginTop: 0 }}>
        <label className="button">
          {has ? t("qimage.replace") : t("qimage.add")}
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
        {has && (
          <button type="button" className="link danger" disabled={busy} onClick={() => remove.mutate()}>
            {t("qimage.remove")}
          </button>
        )}
      </div>
      <ErrorBanner error={upload.error ?? remove.error} />
    </section>
  );
}
