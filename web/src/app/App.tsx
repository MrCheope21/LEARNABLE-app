import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { AuthProvider, useAuth } from "../auth/AuthContext";
import { ResetPasswordPage } from "../auth/PasswordPages";
import { SignInPage } from "../auth/SignInPage";
import { ChapterPage } from "../features/curriculum/ChapterPage";
import { ConceptPage } from "../features/curriculum/ConceptPage";
import { CourseLayout } from "../features/curriculum/CourseLayout";
import { CourseOverview } from "../features/curriculum/CourseOverview";
import { ProposalPage } from "../features/curriculum/ProposalPage";
import { QuestionsPage } from "../features/curriculum/QuestionsPage";
import { WeakSpotsPage } from "../features/curriculum/WeakSpotsPage";
import { GuidePage } from "../features/guide/GuidePage";
import { ListingPage } from "../features/marketplace/ListingPage";
import { MarketplacePage } from "../features/marketplace/MarketplacePage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { I18nProvider } from "../i18n";
import { TopicPage } from "../features/curriculum/TopicPage";
import { CoursesPage } from "../features/courses/CoursesPage";
import { ActivityPage } from "../features/dashboard/ActivityPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { ReviewHubPage } from "../features/home/HomePage";
import { CourseMaterialPage } from "../features/material/MaterialPanel";
import { ProgressPage } from "../features/progress/ProgressPage";
import { StudyPage } from "../features/study/StudyPage";
import { AppShell } from "./AppShell";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        // Retrying a 4xx can't help; a network blip can.
        retry: (count, error) => count < 2 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
        refetchOnWindowFocus: true,
      },
    },
  });
}

function CourseMaterialRoute() {
  const { courseId = "" } = useParams();
  return <CourseMaterialPage courseId={courseId} />;
}

export function AppRoutes() {
  return (
    <I18nProvider>
      <Routes>
        {/* A reset link must open whether or not this browser is signed in. */}
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="*" element={<SignedInRoutes />} />
      </Routes>
    </I18nProvider>
  );
}

function SignedInRoutes() {
  const { isSignedIn } = useAuth();
  if (!isSignedIn) return <SignInPage />;
  return (
    <Routes>
      <Route path="/study/:courseId" element={<StudyPage />} />
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="courses" element={<CoursesPage />} />
        <Route path="courses/:courseId" element={<CourseLayout />}>
          <Route index element={<CourseOverview />} />
          <Route path="chapters/:chapterId" element={<ChapterPage />} />
          <Route path="topics/:topicId" element={<TopicPage />} />
          <Route path="concepts/:conceptId" element={<ConceptPage />} />
          <Route path="proposals/:proposalId" element={<ProposalPage />} />
          <Route path="material" element={<CourseMaterialRoute />} />
          <Route path="questions" element={<QuestionsPage />} />
          <Route path="weak-spots" element={<WeakSpotsPage />} />
        </Route>
        <Route path="review" element={<ReviewHubPage />} />
        <Route path="progress" element={<ProgressPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="guide" element={<GuidePage />} />
        <Route path="marketplace" element={<MarketplacePage />} />
        <Route path="marketplace/:listingId" element={<ListingPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App({ queryClient }: { queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? createQueryClient());
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
