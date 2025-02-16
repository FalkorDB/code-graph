import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function handleZoomToFit(chartRef?: any) {
  const chart = chartRef.current
  if (chart) {
    // Get canvas dimensions
    const canvas = document.querySelector('.force-graph-container canvas.clickable') as HTMLCanvasElement;
    if (!canvas) return;

    const container = canvas.parentElement;

    if (!container) return;

    // Calculate padding as 1% of the smallest canvas dimension
    const minDimension = Math.max(container.clientWidth, container.clientHeight);

    const padding = minDimension * 0.1

    chart.zoomToFit(1000, padding)
  }
}