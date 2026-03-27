import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Mulish", "system-ui", "sans-serif"],
        display: ["Onest", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      colors: {
        brand: {
          orange: "#e3814c",
          "orange-light": "#f0a070",
          "orange-dark": "#c96a35",
          teal: "#008d7f",
          "teal-light": "#00b8a6",
          "teal-dark": "#006b60",
          sky: "#3dabd8",
          gold: "#ecc137",
        },
      },
      boxShadow: {
        glass: "0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.08)",
        "glass-sm": "0 4px 16px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.06)",
        "orange-glow": "0 0 40px rgba(227,129,76,0.25)",
        "teal-glow": "0 0 40px rgba(0,141,127,0.25)",
      },
    },
  },
  plugins: [],
};

export default config;
