export const metadata = {
  title: "GSE Vocabulary Profiler",
  description: "Confidence-weighted GSE vocabulary scoring — paste a sample or upload a batch.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "ui-sans-serif, -apple-system, Segoe UI, Roboto, sans-serif" }}>
        {children}
      </body>
    </html>
  );
}
