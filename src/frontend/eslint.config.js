// Flat config (ESLint 9). Deliberately NOT type-aware: `projectService` would
// pull the whole TypeScript program into every run, which turns a per-file
// lint from ~0.5s into several seconds — and the edit-time Claude Code hook
// (.claude/hooks/lint.sh) runs this on every .ts/.tsx write. `npm run
// typecheck` (tsc --noEmit) is what covers types; this covers what the
// compiler cannot see, chiefly the react-hooks dependency rules.
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist",
      // Generated from the service's OpenAPI document (D23), never edited here.
      "src/types/messaging.ts",
      "openapi",
    ],
  },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // Unused function arguments are normal in callbacks and handlers; an
      // unused *variable* is not.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { args: "none", varsIgnorePattern: "^_" },
      ],
    },
  },
  {
    // Test helpers export functions beside components, and a test file is never
    // hot-reloaded, so Fast Refresh's rule has nothing to protect here.
    files: ["src/test/**", "**/*.test.{ts,tsx}"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
);
