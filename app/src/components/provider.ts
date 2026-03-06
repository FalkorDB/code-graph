import { createContext } from "react";
import { Graph } from "./model";

export const GraphContext = createContext<Graph>(Graph.empty());
