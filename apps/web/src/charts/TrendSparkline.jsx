// src/charts/TrendSparkline.jsx
//
// Tiny lightweight-charts area sparkline used to pair raw metric numbers with
// trend context (Sprint 2). Dark DM Mono aesthetic, no axes/scale chrome.
import React, { useEffect, useRef } from "react";
import { createChart, ColorType, AreaSeries } from "lightweight-charts";

/**
 * @param {Array<{date: string, [seriesKey]: number}>} rows metric history rows
 * @param {string} seriesKey which numeric field to plot (e.g. "accuracy")
 * @param {number} height pixel height of the sparkline canvas
 * @param {string} color line + gradient color (hex)
 */
export default function TrendSparkline({
  rows = [],
  seriesKey = "accuracy",
  height = 48,
  color = "#16a34a",
}) {
  const containerRef = useRef(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true, // re-flow when the responsive card grid changes size
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#6b7280",
        fontFamily: '"DM Mono", monospace',
        fontSize: 10,
        // Hide the TradingView attribution logo (bottom-right corner). Clicking it
        // navigates to tradingview.com, which yanks the user out of the app.
        attributionLogo: false,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { visible: false },
      },
      rightPriceScale: { visible: false },
      timeScale: { visible: false, borderVisible: false },
      handleScroll: false,
      handleScale: false,
      crosshair: {
        vertLine: { visible: false },
        horzLine: { visible: false },
      },
    });

    const data = (rows || [])
      .filter(
        (r) =>
          r?.date &&
          Number.isFinite(Number(r[seriesKey])) &&
          String(r.date).length >= 10,
      )
      .map((r) => ({
        time: String(r.date).slice(0, 10), // "yyyy-mm-dd"
        value: Number(r[seriesKey]),
      }));

    if (data.length) {
      const series = chart.addSeries(AreaSeries, {
        lineColor: color,
        topColor: `${color}44`,
        bottomColor: `${color}00`,
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      series.setData(data);
      chart.timeScale().fitContent();
    }

    return () => {
      chart.remove();
    };
  }, [rows, seriesKey, height, color]);

  return (
    <div ref={containerRef} style={{ width: "100%", height }} />
  );
}
