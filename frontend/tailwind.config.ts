import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: "#102c43",
        turquoise: "#00a99d",
        canvas: "#f5f8f8",
      },
      borderRadius: { card: "1.5rem" },
    },
  },
  plugins: [],
};
export default config;
