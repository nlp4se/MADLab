import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RunSummary } from "@/api";

import { formatCost, formatCount, formatDuration } from "./format";
import {
  InstanceFigures,
  instanceFiguresText,
  RunSummaryBar,
} from "./RunSummaryBar";

/** Run summary formatting + rendering (task 11.18). */

const SUMMARY: RunSummary = {
  wall_time_s: 125.4,
  model_time_s: 98.76,
  input_tokens: 1234567,
  output_tokens: 4321,
  total_tokens: 1238888,
  cost_usd: 0.01234,
  calls: 1500,
  instances: { total: 10, completed: 9, failed: 1 },
};

describe("formatters", () => {
  it("formats durations as ms / s / min / h", () => {
    expect(formatDuration(0.85)).toBe("850 ms");
    expect(formatDuration(0)).toBe("0 ms");
    expect(formatDuration(0.9996)).toBe("1.0 s");
    expect(formatDuration(12.34)).toBe("12.3 s");
    expect(formatDuration(59.97)).toBe("1 min 00 s");
    expect(formatDuration(125.4)).toBe("2 min 05 s");
    expect(formatDuration(3725)).toBe("1 h 02 min");
  });

  it("formats counts with thousands separators and cost in USD", () => {
    expect(formatCount(1234567)).toBe("1,234,567");
    expect(formatCount(0)).toBe("0");
    expect(formatCost(0.01234)).toBe("$0.0123");
    expect(formatCost(12.5)).toBe("$12.50");
    expect(formatCost(0)).toBe("$0.0000");
  });

  it("shows a dash for missing values", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
    expect(formatDuration(Number.NaN)).toBe("—");
    expect(formatCount(null)).toBe("—");
    expect(formatCost(null)).toBe("—");
  });
});

describe("RunSummaryBar", () => {
  it("renders wall time, model time, tokens, cost and calls with the hint", () => {
    render(<RunSummaryBar summary={SUMMARY} />);
    expect(screen.getByTestId("run-summary-wall-time")).toHaveTextContent("2 min 05 s");
    expect(screen.getByTestId("run-summary-model-time")).toHaveTextContent("1 min 39 s");
    expect(screen.getByTestId("run-summary-input-tokens")).toHaveTextContent("1,234,567");
    expect(screen.getByTestId("run-summary-output-tokens")).toHaveTextContent("4,321");
    expect(screen.getByTestId("run-summary-cost")).toHaveTextContent("$0.0123");
    expect(screen.getByTestId("run-summary-calls")).toHaveTextContent("1,500");
    expect(screen.getByText(/Wall time is the clock time/i)).toBeInTheDocument();
    expect(screen.getByText(/Model time adds up the latency/i)).toBeInTheDocument();
  });

  it("shows dashes for an old run without timestamps or cost", () => {
    render(
      <RunSummaryBar
        summary={{ ...SUMMARY, wall_time_s: null, model_time_s: null, cost_usd: null }}
      />,
    );
    expect(screen.getByTestId("run-summary-wall-time")).toHaveTextContent("—");
    expect(screen.getByTestId("run-summary-model-time")).toHaveTextContent("—");
    expect(screen.getByTestId("run-summary-cost")).toHaveTextContent("—");
    // Token totals still come from the stored transcripts.
    expect(screen.getByTestId("run-summary-input-tokens")).toHaveTextContent("1,234,567");
  });

  it("degrades to dashes without any summary", () => {
    render(<RunSummaryBar summary={undefined} />);
    for (const id of ["wall-time", "input-tokens", "output-tokens", "calls"]) {
      expect(screen.getByTestId(`run-summary-${id}`)).toHaveTextContent("—");
    }
  });
});

describe("InstanceFigures", () => {
  const usage = {
    input_tokens: 12345,
    output_tokens: 678,
    total_tokens: 13023,
    cost_usd: null,
    model_time_s: 4.2,
    calls: 3,
  };

  it("shows the debate time and in/out tokens", () => {
    render(<InstanceFigures instance={{ usage, duration_s: 7.25 }} />);
    expect(screen.getByTestId("instance-figures")).toHaveTextContent(
      "7.3 s · 12,345 in / 678 out",
    );
  });

  it("shows a dash for an unrecorded duration and nothing without any data", () => {
    expect(instanceFiguresText({ usage, duration_s: null })).toBe(
      "— · 12,345 in / 678 out",
    );
    expect(instanceFiguresText({ usage: null, duration_s: null })).toBeNull();
    const { container } = render(<InstanceFigures instance={{}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
