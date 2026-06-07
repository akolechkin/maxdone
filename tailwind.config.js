/** Design tokens lifted from the reconstructed MaxDone mockup. */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./tasks/templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        // accent (original MaxDone purple)
        accent: {
          DEFAULT: "#534AB7",
          fg: "#3C3489",
          soft: "#EEEDFE",
        },
        // goal / success teal
        teal: {
          DEFAULT: "#1D9E75",
          fg: "#0F6E56",
          soft: "#E1F5EE",
        },
        ink: {
          DEFAULT: "#2C2C2A",   // text-primary
          muted: "#5F5E5A",     // text-secondary
          faint: "#888780",     // text-tertiary
        },
        surface: {
          DEFAULT: "#FFFFFF",
          alt: "#F7F6F1",       // secondary surface
        },
        line: "rgba(44,44,42,0.15)",   // hairline border
        "line-strong": "rgba(44,44,42,0.3)",
      },
      borderRadius: {
        md: "8px",
        lg: "12px",
        xl: "16px",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      fontWeight: {
        // mockup rule: only 400 and 500
        normal: "400",
        medium: "500",
      },
    },
  },
  plugins: [],
};
