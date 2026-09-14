import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import {
  ExamEntryErrorBanner,
  ExamEntryEmptyExams,
  ExamEntryStatusBlock,
} from "./ExamEntryStatus";

describe("ExamEntryStatus (empty + error)", () => {
  it("error state shows alert with message", () => {
    render(<ExamEntryErrorBanner message="exam load failed" />);
    expect(screen.getByRole("alert")).toHaveTextContent("exam load failed");
  });

  it("empty state shows No exams yet", () => {
    render(<ExamEntryEmptyExams />);
    expect(screen.getByText(/No exams yet/i)).toBeInTheDocument();
  });

  it("status block empty when not loading", () => {
    render(<ExamEntryStatusBlock error={null} loading={false} examCount={0} />);
    const root = screen.getByTestId("exam-entry-status");
    expect(within(root).getByText(/No exams yet/i)).toBeInTheDocument();
  });

  it("status block shows error", () => {
    render(
      <ExamEntryStatusBlock error="exam load failed" loading={false} examCount={0} />
    );
    const root = screen.getByTestId("exam-entry-status");
    expect(within(root).getByRole("alert")).toHaveTextContent("exam load failed");
  });
});
