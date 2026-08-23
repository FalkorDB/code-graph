import FalkorDBCanvas from "@falkordb/canvas"
import { type ClassValue, clsx } from "clsx"
import { MutableRefObject } from "react"
import { twMerge } from "tailwind-merge"

export type PathData = {
  nodes: any[]
  links: any[]
}

export const DEFAULT_BRANCH = "_default"

// A single entry returned by /api/list_repos: `graph` is the underlying
// FalkorDB graph name to query, `project`/`branch` are used for display.
export type RepoOption = {
  project: string
  branch: string
  graph: string
}

// Normalizes a /api/list_repos entry into a RepoOption. Older/production
// backends may still return plain repo name strings instead of
// {project, branch, graph} objects — handle both so the UI never renders
// "undefined (undefined)" or crashes when pointed at a mismatched backend.
export function toRepoOption(entry: unknown): RepoOption {
  if (typeof entry === "string") {
    return { project: entry, branch: DEFAULT_BRANCH, graph: entry }
  }
  const repo = entry as Partial<RepoOption> | null | undefined
  const branch = repo?.branch ?? DEFAULT_BRANCH
  // A backend that reports a project/branch pair without the composed key
  // still has to be queried by that key, otherwise the UI would show the
  // branch but silently load the default one.
  const graph = repo?.graph
    ?? (repo?.project ? composeGraphName(repo.project, branch) : "")
  return {
    project: repo?.project ?? graph,
    branch,
    graph,
  }
}

export function repoLabel(repo: RepoOption): string {
  return repo.branch === DEFAULT_BRANCH ? repo.project : `${repo.project} (${repo.branch})`
}

export function composeGraphName(project: string, branch?: string | null): string {
  return `code:${project}:${branch || DEFAULT_BRANCH}`
}

// Mirrors the backend's `urlparse(url).path.split('/')[-1]`, so the name the
// UI derives for a freshly analyzed repo matches the one the API created.
// Falls back to a plain split for inputs URL() cannot parse.
export function projectNameFromURL(url: string): string {
  try {
    return new URL(url).pathname.split("/").pop() ?? ""
  } catch {
    return url.split("/").pop() ?? ""
  }
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

export const PATH_COLOR = "#ffde21"