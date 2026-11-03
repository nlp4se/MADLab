/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Dimension theming tokens (Reqs 6.6, 7.4): each taxonomy dimension has
        // a fixed colour identity used by panels, badges, tabs, and the
        // designer inspector — Participants (indigo), Interaction (teal),
        // Agreement (amber). Driven by CSS variables so a single theme change
        // propagates everywhere.
        participants: {
          DEFAULT: "hsl(var(--participants))",
          foreground: "hsl(var(--participants-foreground))",
          muted: "hsl(var(--participants-muted))",
        },
        interaction: {
          DEFAULT: "hsl(var(--interaction))",
          foreground: "hsl(var(--interaction-foreground))",
          muted: "hsl(var(--interaction-muted))",
        },
        agreement: {
          DEFAULT: "hsl(var(--agreement))",
          foreground: "hsl(var(--agreement-foreground))",
          muted: "hsl(var(--agreement-muted))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
