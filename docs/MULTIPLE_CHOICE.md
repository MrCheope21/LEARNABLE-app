# Multiple-choice questions

Code: `backend/app/services/learning/choices.py`, `web/src/features/study/ChoicePicker.tsx`.

An item with `choices` (2-8 options, `[{"text", "correct"}]`, at least one correct, no two
alike) has `answer_format = "CHOICE"`. With one correct option the student picks it (radio
buttons); with several they pick exactly those (check boxes). The options are shown in an order
shuffled per question; which are correct is never sent before answering.

## Grading, without AI

`POST /review-sessions/{id}/answers {question_formulation_id, choices: [positions]}`. The server
stores the picked options as the answer's text ("B) Il mutuatario") and writes a deterministic
evaluation (`ai_provider = "choice"`):

| Picked | Classification | Outcome (resolver) |
|---|---|---|
| exactly the correct ones | CORRECT | GOOD |
| some correct, none wrong (several correct) | PARTIALLY_CORRECT | from the resolver |
| any wrong one, or none of the correct | WRONG | AGAIN |

`gap` names the correct options. No AI allowance is used; there is no second opinion (the
student can still grade the answer themselves) and no "review and repeat".

## Making them

- By hand: Manage questions → Edit → "Answered by picking among options". `[]` in
  `PATCH /learning-items/{id} {choices}` turns it back into a written-answer question. When the
  reference answer is empty (or was written by this feature), it becomes "✓ " + the correct
  options; otherwise it stays as an explanation shown after answering.
- Imported (question bank, also from Excel/CSV cells):

  ```
  Domanda: Chi deve restituire il denaro nel mutuo?
  A) Il mutuante
  B) Il mutuatario
  C) Nessuno
  Risposta: B
  ```

  Options are lines starting with a letter and ")" or "." ("A:" and "D:" are already the answer
  and question labels). The answer names letters only: "B", "A, C", "a e b". Anything else stays
  a written-answer question.
- The chatbot prompt in "Add material" explains the format.

Marketplace copies carry the options (they are the author's, read-only); offline packs carry
them with the correct flags, and the device grades them.

Not built: AI generation of multiple-choice questions from material.
