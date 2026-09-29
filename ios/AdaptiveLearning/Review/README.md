Review session logic lives on the backend (docs/SCHEDULING.md): it picks the questions, resolves
outcomes and moves the schedule. The app drives the screens only, in
`Presentation/Study/StudySessionViewModel.swift`, and never computes a memory level or a due date.
