import FalkorDBCanvas from "@falkordb/canvas"
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

export function createMessage(msg: Omit<Message, 'id'>): Message {
  return { ...msg, id: crypto.randomUUID() };
}

export interface Message {
  id: string;
  type: MessageTypes;
  text?: string;
  paths?: { nodes: any[], links: any[] }[];
  graphName?: string;
}

export type GraphRef = MutableRefObject<FalkorDBCanvas | null>

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const PATH_COLOR = "#ffde21"