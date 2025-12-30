import { Link, Node } from "@/app/components/model"
import FalkorDBCanvas, { GraphNode } from "@falkordb/canvas"
import { type ClassValue, clsx } from "clsx"
import { MutableRefObject } from "react"
import { twMerge } from "tailwind-merge"

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

export type GraphRef = MutableRefObject<FalkorDBCanvas | null>

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
