/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        'bg-dark': '#0c0e10',
        'bg-light': '#292929',
        'bg-input': '#393939',
        'bg-workspace': '#1f2228',
        'border': '#3c3c4a',
        'text-editor-base': '#9099ac',
        'text-editor-active': '#c4cbda',
        'bg-editor-sidebar': '#24272e',
        'bg-editor-active': '#31343d',
        'border-editor-sidebar': '#3c3c4a',
      },
      fontFamily: {
        sans: ['-apple-system', 'SF Pro', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', 'sans-serif'],
        mono: ['source-code-pro', 'Menlo', 'Monaco', 'Consolas', 'Courier New', 'monospace'],
      },
    },
  },
  plugins: [],
}
