/** @type {import('tailwindcss').Config} */

// Every colour name below resolves to a CSS variable in src/theme/tokens.css —
// the one place where values live. Names say what a colour is for, not its hue.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`
const status = (c) => ({ bg: v(`st-${c}-bg`), fg: v(`st-${c}-fg`), line: v(`st-${c}-line`) })

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  // the theme class is set on <html> before first paint (index.html)
  darkMode: ['class', '.dark'],
  theme: {
    extend: {
      colors: {
        canvas: v('canvas'),
        surface: { DEFAULT: v('surface'), 2: v('surface-2') },
        line: v('line'),
        fg: { DEFAULT: v('fg'), muted: v('fg-muted') },
        link: v('link'),
        accent: { DEFAULT: v('accent'), ink: v('accent-ink'), hover: v('accent-hover') },
        sidebar: { DEFAULT: v('sidebar'), 2: v('sidebar-2'), fg: v('sidebar-fg'), muted: v('sidebar-muted') },
        danger: { DEFAULT: v('danger'), ink: v('danger-ink') },
        focus: v('focus'),
        st: {
          green: status('green'), yellow: status('yellow'), orange: status('orange'),
          red: status('red'), blue: status('blue'), grey: status('grey'),
        },
      },
      fontFamily: {
        // the cabinet's stack: Tailwind's system sans, no web font
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto',
               'Helvetica Neue', 'Arial', 'sans-serif'],
      },
      borderRadius: {
        card: 'var(--radius-card)',
        control: 'var(--radius-control)',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
      },
    },
  },
  plugins: [],
}
