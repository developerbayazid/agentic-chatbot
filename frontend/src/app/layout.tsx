import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";

import "./globals.css";
import { ThemeProvider } from "@/components/layout/theme-provider";
import { QueryProvider } from "@/components/layout/query-provider";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "BAYAZID AI",
  description:
    "An extensible agentic AI assistant: conversations, retrieval, and human-approved actions.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <ThemeProvider>
          <QueryProvider>
            {children}
            <Toaster
              position="bottom-right"
              toastOptions={{ className: "font-sans" }}
            />
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
