import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import "./globals.css";

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Site screen: edge data center vs. solar | Solar Landscape",
  description:
    "Transparent, fast feasibility screen for sales and real estate teams comparing edge data centers to rooftop solar at commercial properties.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistMono.variable} font-sans antialiased`}>
        {/* Background ambient orbs */}
        <div className="bg-orb w-[600px] h-[600px] top-[-200px] left-[-200px]"
          style={{ background: "radial-gradient(circle, #e3814c, transparent)" }} />
        <div className="bg-orb w-[500px] h-[500px] top-[40%] right-[-150px]"
          style={{ background: "radial-gradient(circle, #008d7f, transparent)" }} />
        <div className="bg-orb w-[400px] h-[400px] bottom-[-100px] left-[30%]"
          style={{ background: "radial-gradient(circle, #3dabd8, transparent)" }} />
        <div className="relative z-10">
          {children}
        </div>
      </body>
    </html>
  );
}
