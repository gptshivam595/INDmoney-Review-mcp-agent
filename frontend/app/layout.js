import "./globals.css";

export const metadata = {
  title: "Review Insights Analyser",
  description: "Dark operations dashboard for the INDMoney review pulse agent.",
};

export default function RootLayout({ children }) {
  return (
    <html className="dark" lang="en">
      <body>{children}</body>
    </html>
  );
}
