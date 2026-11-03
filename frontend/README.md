# Frontend — MAD management webapp

The **frontend** is a React + TypeScript (Vite) single-page application for designing, configuring,
executing, and analysing **Multi-Agent Debate (MAD)** configurations.

## Purpose

- A **visual debate designer** (node/edge canvas) where participants are nodes and communication
  paths are directed edges, kept in sync with the underlying `G=(V,E)` configuration artifact.
- **Exhaustive taxonomy configuration** across the three dimensions — Participants, Interaction,
  Agreement — rendered data-driven from the backend taxonomy API, with sensible defaults and
  progressive disclosure.
- **Provider and credential management**, with write-only API keys.
- **Execution** launching (single ad-hoc instance or dataset batch) and **execution history** with
  per-instance transcript inspection and metrics.

The three taxonomy dimensions are visually and distinctly separated throughout the UI.

> Detailed setup, dependencies, and run instructions are added in later tasks.
