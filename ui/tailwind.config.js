export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#1f1a17',
        muted: '#6f6761',
        surface: '#f3efe8',
        paper: '#fbf9f5',
        line: '#dcd5cb',
        accent: '#b86752',
        accentSoft: '#e7c8bd',
      },
      fontFamily: {
        display: ['"Playfair Display"', 'Georgia', 'serif'],
        body: ['"IBM Plex Sans"', '"Helvetica Neue"', 'Arial', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 10px 30px rgba(31, 26, 23, 0.08)',
        inset: 'inset 0 0 0 1px rgba(31, 26, 23, 0.05)',
      },
      borderRadius: {
        xl: '22px',
      },
    },
  },
  plugins: [],
}
