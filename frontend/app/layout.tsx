import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import { RoleProvider } from "@/lib/role-context";
import { Sidebar, SidebarFallback } from "@/components/Sidebar";
import { Header } from "@/components/Header";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
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
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <RoleProvider>
          <div className="flex h-screen overflow-hidden bg-gray-50">
            {/*
             * Sidebar'ı Suspense içine alıyoruz:
             * usePathname() Next.js 16'da prerender sırasında client-only hook
             * olduğundan, statik SidebarFallback gösterilirken gerçek Sidebar
             * istemci tarafında stream edilir.
             */}
            <Suspense fallback={<SidebarFallback />}>
              <Sidebar />
            </Suspense>

            {/* Sağ içerik alanı */}
            <div className="flex flex-1 flex-col overflow-hidden">
              {/* Üst çubuk */}
              <Header />

              {/* Sayfa içeriği */}
              <main className="flex-1 overflow-y-auto p-6">{children}</main>
            </div>
          </div>
        </RoleProvider>
      </body>
    </html>
  );
}
