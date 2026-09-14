/**
 * Pure status surface for ExamEntry — empty + error (DoD vitest target).
 * Kept separate so tests do not transform the full entry form graph.
 */
export function ExamEntryErrorBanner({ message }: { message: string }) {
  return (
    <div className="warning-banner" role="alert" style={{ marginBottom: 16 }}>
      {message}
    </div>
  );
}

export function ExamEntryEmptyExams() {
  return <span className="caption muted">No exams yet.</span>;
}

export function ExamEntryStatusBlock({
  error,
  loading,
  examCount,
}: {
  error: string | null;
  loading: boolean;
  examCount: number;
}) {
  return (
    <div data-testid="exam-entry-status">
      {error ? <ExamEntryErrorBanner message={error} /> : null}
      {examCount === 0 && !loading ? <ExamEntryEmptyExams /> : null}
    </div>
  );
}
