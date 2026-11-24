import type { Metadata } from "next";
import { Geist_Mono, Inter, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { Suspense } from "react";
import { SessionBoundary } from "@/components/SessionBoundary";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "latin-ext"],
});

const serifHeading = Source_Serif_4({
  variable: "--font-serif-heading",
  subsets: ["latin", "latin-ext"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Miço Usta — Çağrı Analitiği",
  description:
    "Yapay Zekâ Destekli Sesli Asistan ve Çağrı Analitiği Sistemi — Miço Usta entegrasyonu",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body
        className={`${inter.variable} ${serifHeading.variable} ${geistMono.variable} antialiased`}
      >
        <Suspense fallback={null}>
          <SessionBoundary>{children}</SessionBoundary>
        </Suspense>
      </body>
    </html>
  );
}
