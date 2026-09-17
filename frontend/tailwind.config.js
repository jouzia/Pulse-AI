/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Design tokens for an engineering ops console -- deliberately
        // not Tailwind's default slate/gray scale. See
        // docs/architecture.md's dashboard section for the token plan.
        bg: "#0A0C10",
        surface: "#12151B",
        "surface-raised": "#181C24",
        border: "#232833",
        "text-primary": "#E4E7EC",
        "text-secondary": "#8B93A3",
        "text-tertiary": "#5B6472",
        accent: "#4C8DFF",
        "accent-dim": "#1E3252",
        success: "#3FB67F",
        warning: "#D9A544",
        error: "#E5566B",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
