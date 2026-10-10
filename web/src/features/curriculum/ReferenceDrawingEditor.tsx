import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { Schemas } from "../../api/client";
import { learningItems } from "../../api/endpoints";
import { AuthImage } from "../../components/AuthImage";
import { useReadOnlyCourse } from "../../components/CourseAccess";
import { DrawingPad, dataUrlToBlob } from "../../components/DrawingPad";
import { ErrorBanner } from "../../components/QueryState";

type Item = Schemas["LearningItemRead"];

/**
 * "Answer by drawing": the reference drawing that is this question's answer (a molecule, a
 * diagram, a graph). Uploaded as an image, or drawn here. Students then answer by drawing.
 */
export function ReferenceDrawingEditor({ item, onChanged }: { item: Item; onChanged: () => void }) {
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
      <section className="reference-drawing" aria-label="Answer by drawing">
        <h4>Answer by drawing</h4>
        <p className="hint">You answer this question by drawing. The AI compares your drawing with this one.</p>
        <AuthImage queryKey={["reference-drawing", item.id]} load={() => learningItems.referenceDrawing(item.id)} alt="Reference drawing" className="drawing-image" />
      </section>
    ) : null;
  }

  return (
    <section className="reference-drawing" aria-label="Answer by drawing">
      <h4>Answer by drawing</h4>
      {drawn ? (
        <>
          <p className="hint">Students answer this question by drawing. The AI compares their drawing with this one.</p>
          <AuthImage queryKey={["reference-drawing", item.id]} load={() => learningItems.referenceDrawing(item.id)} alt="Reference drawing" className="drawing-image" />
        </>
      ) : (
        <p className="hint">
          For questions answered with a drawing (a molecule, a diagram, a graph): add the correct drawing, and students will
          draw their answer instead of writing it.
        </p>
      )}
      {sketching ? (
        <>
          <DrawingPad onChange={setSketch} disabled={busy} />
          <div className="actions" style={{ marginTop: 0 }}>
            <button type="button" className="primary" disabled={!sketch || busy} onClick={() => sketch && upload.mutate(dataUrlToBlob(sketch))}>
              Save this drawing
            </button>
            <button type="button" className="link" onClick={() => setSketching(false)}>
              Cancel
            </button>
          </div>
        </>
      ) : (
        <div className="actions" style={{ marginTop: 0 }}>
          <label className="button">
            {drawn ? "Replace with an image…" : "Upload the drawing…"}
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
            {drawn ? "Draw a new one" : "Draw it here"}
          </button>
          {drawn && (
            <button type="button" className="link danger" disabled={busy} onClick={() => remove.mutate()}>
              Answer in words instead
            </button>
          )}
        </div>
      )}
      <ErrorBanner error={upload.error ?? remove.error} />
    </section>
  );
}
