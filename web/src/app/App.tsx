import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { AuthProvider, useAuth } from "../auth/AuthContext";
import { ResetPasswordPage } from "../auth/PasswordPages";
import { SignInPage } from "../auth/SignInPage";
import { ChapterPage } from "../features/curriculum/ChapterPage";
import { ConceptPage } from "../features/curriculum/ConceptPage";
import { CourseLayout } from "../features/curriculum/CourseLayout";
import { CourseOverview } from "../features/curriculum/CourseOverview";
import { WeakSpotsPage } from "../features/curriculum/WeakSpotsPage";
import { CommunityPage, ProfilePage } from "../features/community/CommunityPage";
import { NotificationsPage } from "../features/notifications/NotificationsPage";
import { I18nProvider } from "../i18n";
import { TopicPage } from "../features/curriculum/TopicPage";
import { CoursesPage } from "../features/courses/CoursesPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { ReviewHubPage } from "../features/home/HomePage";
import { ReviewQueuePage } from "../features/home/ReviewQueuePage";
import { ProgressPage } from "../features/progress/ProgressPage";
import { AppShell } from "./AppShell";

// Pages most visits never open are fetched when first opened.
const AdminPage = lazy(() => import("../features/admin/AdminPage").then((m) => ({ default: m.AdminPage })));
const ProposalPage = lazy(() => import("../features/curriculum/ProposalPage").then((m) => ({ default: m.ProposalPage })));
const QuestionsPage = lazy(() => import("../features/curriculum/QuestionsPage").then((m) => ({ default: m.QuestionsPage })));
const ChatThreadPage = lazy(() => import("../features/community/ChatPage").then((m) => ({ default: m.ChatThreadPage })));
const CourseLeaderboardPage = lazy(() => import("../features/community/CourseLeaderboardPage").then((m) => ({ default: m.CourseLeaderboardPage })));
const GuidePage = lazy(() => import("../features/guide/GuidePage").then((m) => ({ default: m.GuidePage })));
const ListingPage = lazy(() => import("../features/marketplace/ListingPage").then((m) => ({ default: m.ListingPage })));
const MarketplacePage = lazy(() => import("../features/marketplace/MarketplacePage").then((m) => ({ default: m.MarketplacePage })));
const SalesPage = lazy(() => import("../features/marketplace/SalesPage").then((m) => ({ default: m.SalesPage })));
const SettingsPage = lazy(() => import("../features/settings/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const ActivityPage = lazy(() => import("../features/dashboard/ActivityPage").then((m) => ({ default: m.ActivityPage })));
const CourseMaterialPage = lazy(() => import("../features/material/MaterialPanel").then((m) => ({ default: m.CourseMaterialPage })));
const PrivacyPage = lazy(() => import("../features/privacy/PrivacyPage").then((m) => ({ default: m.PrivacyPage })));
const StudyPage = lazy(() => import("../features/study/StudyPage").then((m) => ({ default: m.StudyPage })));

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
      <Suspense fallback={<div className="state" role="status" aria-busy="true" />}>
      <Routes>
        {/* A reset link must open whether or not this browser is signed in. */}
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="*" element={<SignedInRoutes />} />
      </Routes>
      </Suspense>
    </I18nProvider>
  );
}

function SignedInRoutes() {
  const { isSignedIn } = useAuth();
  if (!isSignedIn) {
    return (
      <Routes>
        <Route path="/privacy" element={<PrivacyPage signedIn={false} />} />
        <Route path="*" element={<SignInPage />} />
      </Routes>
    );
  }
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
          <Route path="leaderboard" element={<CourseLeaderboardPage />} />
        </Route>
        <Route path="review" element={<ReviewHubPage />} />
        <Route path="review/:courseId" element={<ReviewQueuePage />} />
        <Route path="progress" element={<ProgressPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="guide" element={<GuidePage />} />
        <Route path="privacy" element={<PrivacyPage />} />
        <Route path="community" element={<CommunityPage />} />
        <Route path="community/friends" element={<CommunityPage tab="friends" />} />
        <Route path="community/messages" element={<CommunityPage tab="messages" />} />
        <Route path="community/messages/:userId" element={<ChatThreadPage />} />
        <Route path="community/users/:userId" element={<ProfilePage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="marketplace" element={<MarketplacePage />} />
        <Route path="marketplace/sales" element={<SalesPage />} />
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
