import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Doomsday Prep — WW3 Preparedness Platform",
  description: "Real-time regional Doomsday Clock, personalized survival guides, and family preparedness checklists.",
  keywords: ["preparedness", "survival", "WW3", "emergency", "doomsday clock"],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt">
      <body className="min-h-screen bg-[#0a0a0a] text-gray-100 antialiased">
        {children}
        <p className="disclaimer fixed bottom-2 right-2 max-w-xs hidden lg:block">
          Informational purposes only. Not a substitute for official emergency guidance.
        </p>
      </body>
    </html>
  );
}
