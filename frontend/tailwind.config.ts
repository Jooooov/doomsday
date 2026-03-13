import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        fallout: ["var(--font-fallout)", "VT323", "Courier New", "monospace"],
      },
      colors: {
        risk: {
          green: "#22c55e",
          yellow: "#eab308",
          orange: "#f97316",
          red: "#ef4444",
        },
        surface: {
          dark: "#0a0a0a",
          card: "#111111",
          border: "#222222",
        },
      },
    },
  },
  plugins: [],
};

export default config;
