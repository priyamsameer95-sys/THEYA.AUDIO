---
name: mattpocock-typescript
description: Strict TypeScript-first discipline inspired by Matt Pocock (Total TypeScript). Emphasizes clean interface boundaries, discriminated unions, and honest type safety without loose assertions.
---

# Matt Pocock TypeScript Discipline

A collection of strict, practical TypeScript patterns designed to build self-documenting, bulletproof codebases.

## 1. Discriminated Unions over Sprawling Optional Flags
Instead of one giant object with optional properties:
```ts
// ❌ Anti-pattern
interface State {
  status: 'idle' | 'loading' | 'success' | 'error';
  data?: Article;
  error?: string;
}
```
Use discriminated unions that make impossible states unrepresentable:
```ts
// ✅ Best Practice
type State =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: Article }
  | { status: 'error'; error: Error };
```

## 2. Ban `as Type` Assertions
- Avoid `data as Article`. Type assertions lie to the compiler and hide runtime discrepancies.
- Instead, validate boundaries at runtime using type guards, Zod, or ArkType, allowing TypeScript to narrow types automatically.

## 3. Strict Generics & Inferred Types
- Prefer deriving types from single sources of truth (`typeof MY_CONFIG`, `z.infer<typeof Schema>`) rather than manually maintaining duplicate interfaces.
- Constrain generics tightly: `<T extends Record<string, unknown>>` instead of unbounded `<T>`.

## 4. Refactoring Playbook
- Before refactoring a complex module, generate an explicit step-by-step refactor plan.
- Change the type contract first; let the TypeScript compiler guide you to all call sites that need updating.
