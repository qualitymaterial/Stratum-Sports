import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        panel: "var(--panel)",
        panelSoft: "var(--panel-soft)",
        borderTone: "var(--border)",
        textMain: "var(--text-main)",
        textMute: "var(--text-mute)",
        accent: "var(--accent)",
        accentSoft: "var(--accent-soft)",
        positive: "var(--positive)",
        negative: "var(--negative)",
      },
      boxShadow: {
        terminal: "0 0 0 1px rgba(109, 124, 146, 0.18), 0 20px 45px rgba(0, 0, 0, 0.35)",
      },
    },
  },
  plugins: [],
};

export default config;
