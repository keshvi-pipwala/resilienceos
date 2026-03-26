/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#020408",
          900: "#060d1a",
          800: "#0a1628",
          700: "#0f2040",
          600: "#152b55",
        },
        electric: {
          500: "#3b9eff",
          400: "#60aeff",
          300: "#90c8ff",
          600: "#1a7fe0",
        },
        success: "#22c55e",
        warning: "#f59e0b",
        danger: "#ef4444",
        muted: "#4a5568",
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "Fira Code", "monospace"],
        sans: ["'Inter'", "system-ui", "sans-serif"],
      },
      animation: {
        pulse_slow: "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        glow: "glow 2s ease-in-out infinite alternate",
        "fade-in": "fadeIn 0.3s ease-out",
      },
      keyframes: {
        glow: {
          from: { boxShadow: "0 0 5px #3b9eff40" },
          to: { boxShadow: "0 0 20px #3b9eff80, 0 0 40px #3b9eff40" },
        },
        fadeIn: {
          from: { opacity: 0, transform: "translateY(4px)" },
          to: { opacity: 1, transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
