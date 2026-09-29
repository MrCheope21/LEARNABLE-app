import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { tokenStore } from "../api/client";
import { AppRoutes } from "../app/App";
import { AuthProvider } from "../auth/AuthContext";

/** Renders the real app routes at `path`, signed in, with a fresh query cache. */
export function renderApp(path: string, { signedIn = true } = {}) {
  if (signedIn) tokenStore.set("test-token");
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}
