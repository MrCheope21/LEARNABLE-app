import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { failWith, mockApi, ok } from "../test/mockApi";
import { renderApp } from "../test/render";

const ACCEPTED = { detail: "If an account exists for this email, a link to reset its password is on its way." };

describe("passwords", () => {
  it("asks for a reset link from the sign-in page", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([["POST", /\/auth\/password-reset\/request$/, ok(ACCEPTED)]]);
    renderApp("/", { signedIn: false });

    await user.click(screen.getByRole("button", { name: "Forgot your password?" }));
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));

    // The screen words it in the interface language, the same whether or not the account exists.
    expect(await screen.findByText(/If an account exists for this email, a link to reset its password is on its way\./)).toBeInTheDocument();
    expect(requests[0]?.body).toEqual({ email: "ada@example.com" });
    await user.click(screen.getByRole("button", { name: "Back to sign in" }));
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("sets a new password from the emailed link, even when signed out", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([["POST", /\/auth\/password-reset\/confirm$/, () => ({ status: 204 })]]);
    renderApp("/reset-password?token=abcdefghijklmnopqrstuvwxyz0123456789", { signedIn: false });

    await user.type(screen.getByLabelText("New password"), "a-long-new-password");
    await user.type(screen.getByLabelText("Repeat the new password"), "a-long-new-passwor");
    expect(screen.getByText("The two passwords don't match.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set new password" })).toBeDisabled();
    await user.type(screen.getByLabelText("Repeat the new password"), "d");
    await user.click(screen.getByRole("button", { name: "Set new password" }));

    expect(await screen.findByText(/Your password has been changed/)).toBeInTheDocument();
    expect(requests[0]?.body).toEqual({ token: "abcdefghijklmnopqrstuvwxyz0123456789", new_password: "a-long-new-password" });
  });

  it("explains an expired or used link", async () => {
    const user = userEvent.setup();
    mockApi([
      [
        "POST",
        /\/auth\/password-reset\/confirm$/,
        () => ({
          status: 422,
          body: {
            error_type: "validation_error",
            message: "This reset link is invalid or has expired. Ask for a new one.",
            details: { reason: "invalid_reset_token" },
          },
        }),
      ],
    ]);
    renderApp("/reset-password?token=abcdefghijklmnopqrstuvwxyz0123456789", { signedIn: false });
    await user.type(screen.getByLabelText("New password"), "a-long-new-password");
    await user.type(screen.getByLabelText("Repeat the new password"), "a-long-new-password");
    await user.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This reset link is invalid or has expired");
  });

  it("changes the password from Settings, reached from the account menu, and keeps this browser signed in", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi([
      ["GET", /\/dashboard$/, failWith(503, "internal_error")],
      ["GET", /\/auth\/me$/, ok({ id: "u1", email: "ada@example.com", timezone: "UTC", daily_goal: 20, language: "en", display_name: null })],
      ["POST", /\/auth\/change-password$/, ok({ access_token: "fresh-token", token_type: "bearer" })],
    ]);
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Account" }));
    await user.click(screen.getByRole("link", { name: "Settings" }));
    await user.click(await screen.findByRole("button", { name: "Change password" }));
    await user.type(screen.getByLabelText("Current password"), "old-password");
    await user.type(screen.getByLabelText("New password (12+ characters)"), "a-long-new-password");
    await user.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByText(/Password changed/)).toBeInTheDocument();
    expect(requests.find((r) => r.path.endsWith("/change-password"))?.body).toEqual({
      current_password: "old-password",
      new_password: "a-long-new-password",
    });
    await waitFor(() => expect(localStorage.getItem("learnable.accessToken")).toBe("fresh-token"));
  });
});
