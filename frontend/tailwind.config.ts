import type { Config } from "tailwindcss";

// 토큰 출처: 루트 DESIGN.md (먹색 + 노랑 하나. 다른 색 추가 금지)
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        honey: "#ffdb5b",
        pollen: "#fff386",
        ink: "#202020",
        mist: "#f3f3f3",
        charcoal: "#3b3b3b",
        graphite: "#575656",
      },
      fontFamily: {
        sans: ["Pretendard Variable", "Pretendard", "system-ui", "sans-serif"],
      },
      fontSize: {
        caption: ["15px", { lineHeight: "1.5", letterSpacing: "0.11px" }],
        body: ["17px", { lineHeight: "1.5", letterSpacing: "0.2px" }],
        sub: ["20px", { lineHeight: "1.33", letterSpacing: "0.32px" }],
        "h-sm": ["24px", { lineHeight: "1.25", letterSpacing: "0.43px" }],
        h: ["32px", { lineHeight: "1.2", letterSpacing: "0.64px" }],
        "h-lg": ["40px", { lineHeight: "1.18", letterSpacing: "0.8px" }],
      },
      borderRadius: { sm: "9px", btn: "16px", card: "24px" },
      boxShadow: { sm: "rgba(32, 32, 32, 0.12) 0px 1px 8px 0px" },
      keyframes: { marquee: { to: { transform: "translateX(-50%)" } } },
      animation: { marquee: "marquee 30s linear infinite" },
    },
  },
  plugins: [],
};

export default config;
