/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Paleta principal — verde musgo, sóbrio e elegante
        // Inspiração: apresentação institucional MedPag
        brand: {
          50: "#f5f7ef",
          100: "#e8eed6",
          200: "#d2daad",
          300: "#b6c283",
          400: "#9cab63",
          500: "#82924b",
          600: "#687839",
          700: "#525f30",
          800: "#424c2a",
          900: "#353d24",
          950: "#1f2412",
        },
        // Acento — dourado champagne, transmite premium e qualidade
        accent: {
          50: "#fdf8e7",
          100: "#fbedb8",
          200: "#f6dc83",
          300: "#f0c64a",
          400: "#e9b22a",
          500: "#d29215",
          600: "#b27512",
          700: "#8e5a13",
          800: "#744817",
          900: "#623c19",
        },
        // Verde sage para indicadores de "aprovado" (mantém legibilidade visual)
        success: "#5b8138",
        // Semáforo
        warning: "#d97706",
        danger: "#b91c1c",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        serif: ["Georgia", "serif"],
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(circle at center, var(--tw-gradient-stops))",
        // Hero: verde musgo profundo com toque dourado
        "hero-gradient":
          "linear-gradient(135deg, #1f2412 0%, #353d24 40%, #525f30 100%)",
        "gold-shine":
          "linear-gradient(135deg, #f0c64a 0%, #d29215 50%, #8e5a13 100%)",
      },
      animation: {
        "fade-in-up": "fadeInUp 0.6s ease-out",
        "fade-in": "fadeIn 0.4s ease-out",
        "float": "float 6s ease-in-out infinite",
        "shimmer": "shimmer 3s linear infinite",
      },
      keyframes: {
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(20px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
    },
  },
  plugins: [],
};
