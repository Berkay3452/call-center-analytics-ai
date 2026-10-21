import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import { RoleProvider } from "@/lib/role-context";
import { ThemeProvider } from "@/lib/theme-context";
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
    <html lang="tr" suppressHydrationWarning>
      <head>
        {/* Erken tema betiği: FOUC (Flash of Unstyled Content) engeller */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){
              try {
                var t = localStorage.getItem('mico-theme') || 'system';
                var d = t === 'dark' || (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
                if (d) { document.documentElement.classList.add('dark'); }
                else { document.documentElement.classList.remove('dark'); }
              } catch(e) {}
            })();`,
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased overflow-x-hidden`}
      >
        <ThemeProvider>
          <RoleProvider>
            <div className="flex h-screen w-full overflow-hidden bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors">
              {/* Sidebar */}
              <Suspense fallback={<SidebarFallback />}>
                <Sidebar />
              </Suspense>

              {/* Sağ içerik alanı */}
              <div className="flex flex-1 flex-col overflow-hidden min-w-0">
                {/* Üst çubuk */}
                <Header />

                {/* Sayfa içeriği */}
                <main className="flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6 bg-slate-50 dark:bg-slate-950 transition-colors min-w-0">
                  {children}
                </main>
              </div>
            </div>
          </RoleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
