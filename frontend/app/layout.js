import "./globals.css";

export const metadata = {
  title: "Weekly Product Review Pulse",
  description: "Operator dashboard for the weekly product review agent.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
