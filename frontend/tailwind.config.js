/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#050d1f', 900: '#081530', 850: '#0a1a3a', 800: '#0d2147', 700: '#123064', 600: '#1a417f' },
        line: { DEFAULT: '#1d4f93', soft: '#173b70', glow: '#2f7fe0' },
        sky: { accent: '#3cc4ff' },
        num: '#ffc23d',
        ok: '#2ed47a',
        warn: '#ffb020',
        crit: '#ff4d4f',
        txt: { DEFAULT: '#e6eefc', dim: '#8fa6c9', mute: '#5f7aa3' },
      },
      fontFamily: {
        sans: ['"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        din: ['Bahnschrift', '"DIN Alternate"', '"Roboto Condensed"', '"Arial Narrow"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
