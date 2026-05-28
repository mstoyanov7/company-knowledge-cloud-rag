type LoadingStateProps = {
  label: string;
};

export function LoadingState({ label }: LoadingStateProps) {
  return (
    <main className="app-shell app-shell--centered">
      <div className="loading-state" role="status">
        <span className="loading-state__spinner" aria-hidden="true" />
        <span>{label}</span>
      </div>
    </main>
  );
}
