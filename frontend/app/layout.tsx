import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Pulse — Operations Console",
  description: "Internal operations dashboard for the Pulse notification system.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="flex bg-bg font-sans text-text-primary antialiased">
        <Sidebar />
        <main className="min-h-screen flex-1 overflow-y-auto px-8 py-6">{children}</main>
      </body>
    </html>
  );
}
