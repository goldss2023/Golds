import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Midas Markets | AI Trading Intelligence",
  description: "Premium AI trading intelligence, VIP crypto access, and weekly market proof."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
