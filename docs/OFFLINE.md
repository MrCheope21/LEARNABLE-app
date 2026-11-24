# Reviewing offline

Code: `backend/app/services/review/offline.py`, `web/src/features/offline/`.

## What the student does

On the Review page, "Download for offline review" keeps a course on the device: the questions
due now or in the next 7 days (at most 500) with their reference answers. Without a network the
app still opens (service worker) and the banner at the top lists the downloaded courses. Offline
there is no AI: the student reads the question, may write an answer, shows the reference answer
and grades themselves (Again / Hard / Good / Easy). Questions due later can be reviewed ahead.

Answers wait on the device (localStorage) and are sent as soon as it is back online, or with
"Send now". After sending, the pack is downloaded again so its due dates are current.

## What the server does

```
GET  /api/v1/courses/{course_id}/offline-pack   # {course_id, title, created_at, until, cards[]}
POST /api/v1/courses/{course_id}/offline-sync   # {answers: [{client_id, learning_item_id,
                                                #   question_formulation_id, text, outcome,
                                                #   answered_at}]} → {applied, skipped}
```

Each answer is applied as a self-graded scheduled review at the moment it was given
(`answered_at`): schedule, review history, XP (self-graded, so no correctness bonus) and the
day's activity, in one session per sync. It is skipped, never applied, when:

- it was already sent (`client_id`, kept as `override_note = "offline:<client_id>"`);
- the item was reviewed after that moment (on another device): that review stands;
- the item is gone, paused, back to new, or not in the course;
- `answered_at` is in the future or older than 30 days.

## Limits

- Drawing questions are asked offline too, but answered on paper and self-graded.
- New material (consolidation) needs the network: only items already learned are packed.
- The pack's due dates are those of the moment it was downloaded.
