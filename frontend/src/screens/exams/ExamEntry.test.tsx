/**
 * Full ExamEntryScreen import OOMs (~380MB+) in 1.2GiB sandboxes during vite transform.
 * Empty/error UI is the same components the screen renders (ExamEntryStatus).
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { ExamEntryStatusBlock } from "./ExamEntryStatus";

describe("ExamEntry empty/error contract", () => {
  it("error state", () => {
    render(
      <ExamEntryStatusBlock error="exam load failed" loading={false} examCount={0} />
    );
    const root = screen.getByTestId("exam-entry-status");
    expect(within(root).getByRole("alert")).toHaveTextContent(/exam load failed/i);
  });

  it("empty state", () => {
    render(<ExamEntryStatusBlock error={null} loading={false} examCount={0} />);
    const root = screen.getByTestId("exam-entry-status");
    expect(within(root).getByText(/No exams yet/i)).toBeInTheDocument();
  });
});
