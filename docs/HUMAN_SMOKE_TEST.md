# Human Smoke Test

One person, one course, real material, about 30 minutes, in **two sittings**: the scheduled
review becomes due 4 hours after learning (Level 1 of the ladder). Run the Web path and the
iOS path separately, each with its own new course.

Automated runs prove the flow works. This checks whether a person can use it without help.

## Before you start

- A backend running the branch under test, reachable from the browser and the simulator or
  device (docs/DEVELOPMENT.md).
- AI: `AI_PROVIDER=mock` checks the flow only (the mock's curriculum and grading are mechanical).
  With a real provider, note which one and which model the proposal and the feedback name.
- Your own short study material: 1–3 pages of Markdown, text or PDF on a subject you know well
  enough to judge the AI's questions and grades.
- Don't read the implementation docs first. Note what you had to guess.

**Result codes:**

- **PASS**: works, and it was obvious what to do.
- **FAIL**: wrong result or an error.
- **UX ISSUE**: works, but confusing, slow or ugly. Say what you expected.
- **BLOCKER**: you can't continue.

Record one code per step. Add a note for anything other than PASS.

## Web (desktop browser)

Tester: ______ · Date: ______ · Browser: ______ · Backend commit: ______ · AI: ______

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| W1 | Sign in, create a course | The course opens with an empty curriculum | | |
| W2 | Add a chapter, upload your material to it | Status reaches **Ready**; a failure says why | | |
| W3 | Open the source | The passages are your text, readable, in order | | |
| W4 | Analyze the material (AI proposal) | A proposal with topics and concepts, each citing a source | | |
| W5 | Edit the proposal: rename one topic, remove one concept, then accept | The tree shows exactly your edits | | |
| W6 | Open a concept, activate it | Learning items appear (may take a few seconds); a failure offers Try Again | | |
| W7 | Learn now | The introduction explains the item; the source opens from it | | |
| W8 | Answer the recall question in your own words, submit | Feedback: grade, reference answer, sources, next review time | | |
| W9 | Judge the grade: is it fair? | Write the grade and whether you agree | | |
| W10 | Open the source from the feedback | It's the passage the answer should come from | | |
| W11 | Disagree with the grade, pick another | The new grade and a new next-review time are shown | | |
| W12 | Finish the session; open Progress | Curriculum and memory progress changed plausibly | | |
| W13 | Reload the page and sign in again if asked | Everything above is still there | | |
| — | **Second sitting, 4+ hours later** | | | |
| W14 | Today / Review shows the item due | The due count matches what you learned | | |
| W15 | Start the scheduled review, answer | The question isn't a copy of the introduction text | | |
| W16 | Evaluation and source | As W8–W10 | | |
| W17 | Override again if you disagree | As W11 | | |
| W18 | Next review | Later than the first interval if you answered well | | |
| W19 | Progress and history | Level and next review changed; nothing duplicated | | |

## iOS (simulator or device)

Tester: ______ · Date: ______ · Device/iOS: ______ · Backend commit: ______ · AI: ______

| # | Step | Expected | Result | Notes |
|---|---|---|---|---|
| I1 | Sign in (answer the system "Save Password?" prompt either way), create a course | The course opens | | |
| I2 | Add a chapter, import your material from Files | Status reaches **Ready**; a failure says why | | |
| I3 | Open the source | Your text, readable | | |
| I4 | Generate the curriculum proposal | Topics and concepts with sources | | |
| I5 | Edit it (rename, remove), apply | The tree shows your edits | | |
| I6 | Open a concept, activate it | Learning items appear; a failure offers Try Again | | |
| I7 | Learn Now | Introduction; the source opens and closes | | |
| I8 | Type an answer, submit | Feedback with grade, reference, sources, next review | | |
| I9 | Judge the grade | Write it down and whether you agree | | |
| I10 | Open the source from the feedback | The right passage | | |
| I11 | Disagree, pick another grade | "Graded by you" and a new next review | | |
| I12 | Finish; Home and Progress tabs | Plausible figures | | |
| I13 | Kill the app and reopen | Still signed in, same data | | |
| — | **Second sitting, 4+ hours later** | | | |
| I14 | Review tab shows the item due | Count matches | | |
| I15 | Scheduled review: answer | A real recall question | | |
| I16 | Evaluation and source | As I8–I10 | | |
| I17 | Override if you disagree | As I11 | | |
| I18 | Next review | Plausible | | |
| I19 | Progress | Level and next review changed; nothing duplicated | | |

## Summary

- Blockers: ______
- Fails: ______
- Top three UX issues: ______
- Grades you disagreed with (question, your answer, the grade, why): ______
- Would you use this to study for a real exam? Why or why not: ______
