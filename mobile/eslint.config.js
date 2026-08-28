// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require("eslint-config-expo/flat");

// Token-adoption gate (Nocturne v2). Bans raw numeric spacing/typography/
// radius literals and raw hex colors in style props, so bypassing the
// theme is no longer the path of least resistance. See src/theme/primitives.tsx.
//
// Every screen migrated off inline numeric styles in the Phase 3 rebuild
// (Nocturne v2 plan) — severity is "error" so a regression fails `npm run lint`.
const noRawSpacingOrType = {
  selector:
    "Property[key.name=/^(padding|margin|fontSize|gap|rowGap|columnGap|borderRadius)([A-Z]|$)/] > Literal[raw=/^-?\\d/]",
  message:
    "Raw numeric padding/margin/gap/fontSize/borderRadius — use theme.spacing / theme.type via <Box>/<Stack>/<Text> or useStyles(t => ...) instead.",
};

const noRawHexColor = {
  selector: "Literal[value=/^#([0-9a-fA-F]{3}){1,2}([0-9a-fA-F]{2})?$/]",
  message: "Raw hex color — use a theme token (theme.colors / theme.chart / theme.status) instead.",
};

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*"],
  },
  {
    // App/component code: no numeric style literals, no raw hex.
    files: ["src/app/**/*.{ts,tsx}", "src/components/**/*.{ts,tsx}", "src/features/**/*.{ts,tsx}"],
    ignores: [
      // SVG chart geometry (stroke widths, marker radii, coordinate math)
      // isn't layout spacing or typography — exempt, not exhausted.
      "src/components/charts/**",
    ],
    rules: {
      "no-restricted-syntax": ["error", noRawSpacingOrType, noRawHexColor],
    },
  },
  {
    // Token source files may freely define the raw values everything else
    // is banned from writing.
    files: ["src/theme/tokens.ts", "src/theme/primitives.tsx", "src/theme/useStyles.ts", "src/theme/ThemeProvider.tsx"],
    rules: {
      "no-restricted-syntax": "off",
    },
  },
]);
