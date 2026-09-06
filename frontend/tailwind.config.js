/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        flood: {
          50: "#e8f4fc",
          100: "#c5e4f7",
          500: "#1e88e5",
          700: "#1565c0",
          900: "#0d47a1",
        },
      },
    },
  },
  plugins: [],
};
