import { Link, Node } from "@/app/components/model"
import { type ClassValue, clsx } from "clsx"
import { MutableRefObject } from "react"
import { twMerge } from "tailwind-merge"
import { ForceGraphMethods } from "react-force-graph-2d"

export type PathData = {
  nodes: any[]
  links: any[]
}

export type PathNode = {
  id?: number
  name?: string
}

export type Path = {
  start?: PathNode,
  end?: PathNode
}

export enum MessageTypes {
  Query,
  Response,
  Path,
  PathResponse,
  Pending,
  Text,
}

export interface Message {
  type: MessageTypes;
  text?: string;
  paths?: { nodes: any[], links: any[] }[];
  graphName?: string;
}

export type GraphRef = MutableRefObject<ForceGraphMethods<Node, Link> | undefined>

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function handleZoomToFit(chartRef?: any) {
  const chart = chartRef.current
  if (chart) {
    // Find the currently visible canvas by checking display property
    const canvases = document.querySelectorAll('.force-graph-container canvas') as NodeListOf<HTMLCanvasElement>;
    const container = Array.from(canvases).find(canvas => {
      const container = canvas.parentElement;
      
      if (!container) return false;

      // Check if element is actually in viewport
      const rect = container.getBoundingClientRect();
      const isInViewport = rect.width > 0 &&
        rect.height > 0 &&
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= window.innerHeight &&
        rect.right <= window.innerWidth;

      return isInViewport;
    })?.parentElement;

    if (!container) return;

    // Calculate padding as 10% of the smallest canvas dimension
    const minDimension = Math.min(container.clientWidth, container.clientHeight);
    const padding = minDimension * 0.1;

    chart.zoomToFit(1000, padding);
  }
}