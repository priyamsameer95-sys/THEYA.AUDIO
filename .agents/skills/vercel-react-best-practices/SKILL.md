---
name: vercel-react-best-practices
description: Production-grade React, Next.js, and React Native engineering patterns. Covers component structure, proper hook usage, data fetching, error boundaries, and state hygiene.
---

# Vercel React Best Practices

A guide to writing clean, performant, and resilient React and Next.js applications that work properly both in isolation and in full system context.

## 1. Component Architecture & Props
- **Single Responsibility:** Each component should render one distinct UI piece or provide one clear behavioral context.
- **Explicit Prop Contracts:** Always define strict TypeScript interfaces or types for props. Avoid loose `any` or sprawling unconstrained object types.
- **Composition over Inheritance:** Use `children`, render props, or slot patterns rather than giant monolithic components with 20 boolean flags.

## 2. Proper Hook Hygiene & Side Effect Control
- **No Mystery Side Effects:** Never use `useEffect` for data synchronization that can be derived directly during render (`const fullName = firstName + ' ' + lastName`).
- **Dependency Arrays:** Always include all referenced values in `useEffect`, `useCallback`, and `useMemo` dependency arrays. Never disable `react-hooks/exhaustive-deps` without an explicit, documented invariant.
- **Custom Hooks for Reusable Logic:** Extract complex state workflows, event listeners, or network polling into cohesive custom hooks (`useArticleQueue`, `useLocalStorage`).

## 3. Data Fetching & State Colocation
- **Colocate State with Consumers:** Keep state as close as possible to the components that read and write it. Avoid lifting state to the global level unless multiple distant subtrees genuinely share it.
- **Server Components vs. Client Components:** In Next.js App Router, default to Server Components for data fetching and static markup. Use `'use client'` only where interactive state (`useState`, `useEffect`) or browser APIs are needed.
- **Loading & Error States:** Every network or async boundary must render explicit loading skeletons/indicators and catch failures gracefully.

## 4. Error Boundaries
- Wrap critical UI sections in React Error Boundaries so that a crash in one widget does not blank out the entire application.
- Provide a clear fallback UI with a retry trigger.
