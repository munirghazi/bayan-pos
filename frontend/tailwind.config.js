/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        cairo: ['Cairo', 'sans-serif'],
      },
      borderRadius: {
        DEFAULT: 'var(--radius, 0.25rem)',
        md: 'var(--radius-md, 0.375rem)',
        lg: 'var(--radius-lg, 0.5rem)',
        xl: 'var(--radius-xl, 0.75rem)',
        '2xl': 'var(--radius-2xl, 1rem)',
      },
      colors: {
        primary: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
        },
        bayan: {
          green: 'rgb(var(--brand-primary-rgb, 34 84 164) / <alpha-value>)',
          dark: 'rgb(var(--brand-dark-rgb, 28 69 135) / <alpha-value>)',
          light: 'rgb(var(--brand-light-rgb, 229 235 244) / <alpha-value>)',
          gold: 'rgb(var(--brand-accent-rgb, 77 186 127) / <alpha-value>)',
        },
        alkashi: {
          DEFAULT: 'rgb(var(--brand-primary-rgb, 34 84 164) / <alpha-value>)',
          dark: 'rgb(var(--brand-dark-rgb, 28 69 135) / <alpha-value>)',
          light: 'rgb(var(--brand-light-rgb, 229 235 244) / <alpha-value>)',
          gold: 'rgb(var(--brand-accent-rgb, 77 186 127) / <alpha-value>)',
        }
      }
    },
  },
  plugins: [],
}
