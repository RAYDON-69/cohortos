import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ExamAnalyticsScreen } from "./ExamAnalytics";

vi.mock("../../i18n/LocaleContext", () => ({
  useLocale: () => ({ t: (k: string) => k, locale: "en" }),
}));
vi.mock("../../shell/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("../../nav/deskNav", () => ({ buildDeskNav: () => [] }));
vi.mock("../../api/client", () => ({
  loadTokens: () => ({ tenant_id: "t-1" }),
  listBatches: vi.fn(),
  getTopicHeatmap: vi.fn(),
  getStruggleList: vi.fn(),
}));

describe("ExamAnalyticsScreen", () => {
  beforeEach(() => vi.clearAllMocks());

  it("empty topic state", async () => {
    const api = await import("../../api/client");
    (api.listBatches as ReturnType<typeof vi.fn>).mockResolvedValue({
      batches: [{ id: "b1", name: "Batch A" }],
    });
    (api.getTopicHeatmap as ReturnType<typeof vi.fn>).mockResolvedValue({ topics: [] });
    (api.getStruggleList as ReturnType<typeof vi.fn>).mockResolvedValue({ students: [] });
    render(
      <MemoryRouter>
        <ExamAnalyticsScreen />
      </MemoryRouter>
    );
    await waitFor(() =>
      expect(screen.getByText(/No topic results yet/i)).toBeInTheDocument()
    );
  });

  it("error state", async () => {
    const api = await import("../../api/client");
    (api.listBatches as ReturnType<typeof vi.fn>).mockRejectedValue({ detail: "analytics offline" });
    (api.getTopicHeatmap as ReturnType<typeof vi.fn>).mockResolvedValue({ topics: [] });
    (api.getStruggleList as ReturnType<typeof vi.fn>).mockResolvedValue({ students: [] });
    render(
      <MemoryRouter>
        <ExamAnalyticsScreen />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/analytics offline/i)).toBeInTheDocument());
  });
});
