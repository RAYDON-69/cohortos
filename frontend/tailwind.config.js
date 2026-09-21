/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: { DEFAULT: "#FBF9F3", 100: "#F3F0E8" },
        sage: {
          100: "#EAF1DF",
          200: "#DDEACB",
          300: "#C2D8B9",
          500: "#93AC7C",
          700: "#5C7548",
          900: "#2E3A24",
        },
        slate: { 500: "#738290", 700: "#546270" },
        peri: { 300: "#A1B5D8", bg: "#EDF1F9", text: "#4A5D82" },
        ink: "#2B2E28",
        border: { DEFAULT: "#DDE4D2", strong: "#C5D0B8" },
        error: { DEFAULT: "#B3554A", bg: "#F7E9E7" },
        gold: { 500: "#B98A2E", 700: "#8A6620", bg: "#FBF0DA" },
      },
      fontFamily: {
        display: ['"Fraunces"', "Georgia", "serif"],
        body: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "monospace"],
      },
      boxShadow: {
        soft: "0 4px 16px rgba(46, 58, 36, 0.08)",
      },
      borderRadius: {
        card: "12px",
      },
    },
  },
  plugins: [],
};
