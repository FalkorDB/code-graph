import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import CytoscapeComponent from 'react-cytoscapejs'
import { useContext, useRef, useState } from "react";
import { Node } from "./model";
import { RESPOSITORIES } from "../api/repo/repositories";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CircleDot, XCircle, ZoomIn, ZoomOut } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Chat } from "./chat";
import { GraphContext } from "./provider";

const LIMITED_MODE = process.env.NEXT_PUBLIC_MODE?.toLowerCase()==='limited';

// The stylesheet for the graph
const STYLESHEET: cytoscape.Stylesheet[] = [
    {
        selector: "core",
        style: {
            'active-bg-size':0,  // hide gray circle when panning
            // All of the following styles are meaningless and are specified
            // to satisfy the linter...
            'active-bg-color': 'blue',
            'active-bg-opacity': 0.3,
            "selection-box-border-color": 'blue',
            "selection-box-border-width": 0,
            "selection-box-opacity": 1,
            "selection-box-color": 'blue',
            "outside-texture-bg-color": 'blue',
            "outside-texture-bg-opacity":1,
        },
    },
    {
        selector: "node",
        style: {
            label: "data(name)",
            "text-valign": "center",
            "text-halign": "center",
            shape: "ellipse",
            height: 10,
            width: 10,
            "border-width": 0.15,
            "border-opacity": 0.5,
            "background-color": "data(color)",
            "font-size": "3",
            "overlay-padding": "1px",
        },
    },
    {
        selector: "node:active",
        style: {
            "overlay-opacity": 0,  // hide gray box around active node
        },
    },
    {
        selector: "edge",
        style: {
            width: 0.5,
            "line-color": "#ccc",
            "arrow-scale": 0.3,
            "target-arrow-shape": "triangle",
            label: "data(label)",
            'curve-style': 'straight',
            "text-background-color": "#ffffff",
            "text-background-opacity": 1,
            "font-size": "3",
            "overlay-padding": "2px",
        },
    },
]

const LAYOUT = {
    name: "cose",
    fit: true,
    padding: 30,
    avoidOverlap: true,
}

export function CodeGraph(parmas: { onFetchGraph: (url: string) => void, onFetchNode: (node: Node) => Promise<any[]> }) {

    let graph = useContext(GraphContext)
    
    // Holds the user input while typing
    const [url, setURL] = useState('');

    // A reference to the chart container to allowing zooming and editing
    const chartRef = useRef<cytoscape.Core | null>(null)

    // A function that handles the change event of the url input box
    async function handleRepoInputChange(event: any) {

        // If the user pressed enter, submit the URL
        if (event.key === "Enter") {
            await handleSubmit(event);
        }

        // Get the new value of the input box
        let value: string = event.target.value;

        // Update the url state
        setURL(value);
    }

    // A function that handles the click event
    async function handleSubmit(event: any) {
        event.preventDefault();
        parmas.onFetchGraph(url);
    }

    function handleZoomClick(changefactor: number) {
        let chart = chartRef.current
        if (chart) {
            chart.zoom(chart.zoom() * changefactor)
        }
    }

    function handleCenterClick() {
        let chart = chartRef.current
        if (chart) {
            chart.fit()
            chart.center()
        }
    }

    function onRepoSelected(value: string): void {
        setURL(value)
        parmas.onFetchGraph(url)
    }

    return (
        <>
            <header className="border p-4">
                <form className="flex flex-row gap-2" onSubmit={handleSubmit}>
                    <Select onValueChange={onRepoSelected}>
                        <SelectTrigger className={LIMITED_MODE?"border":"border w-2/3"}>
                            <SelectValue placeholder="Suggested repositories" />
                        </SelectTrigger>
                        <SelectContent>
                            {
                                RESPOSITORIES.map((question, index) => {
                                    return <SelectItem key={index} value={question}>{question}</SelectItem>
                                })
                            }
                        </SelectContent>
                    </Select>
                    {
                        !LIMITED_MODE && <Input placeholder="Github repo URL" className="border" type="url" onChange={handleRepoInputChange} />
                    }
                    <Button type="submit">Send</Button>
                </form>
            </header>
            <main className="h-full w-full">
                <div className="flex flex-row" >
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger className="text-gray-600 dark:text-gray-400 rounded-lg border border-gray-300 p-2" onClick={() => handleZoomClick(1.1)}><ZoomIn /></TooltipTrigger>
                            <TooltipContent>
                                <p>Zoom In</p>
                            </TooltipContent>
                        </Tooltip>
                        <Tooltip>
                            <TooltipTrigger className="text-gray-600 dark:text-gray-400 rounded-lg border border-gray-300 p-2" onClick={() => handleZoomClick(0.9)}><ZoomOut /></TooltipTrigger>
                            <TooltipContent>
                                <p>Zoom Out</p>
                            </TooltipContent>
                        </Tooltip>
                        <Tooltip>
                            <TooltipTrigger className="text-gray-600 dark:text-gray-400 rounded-lg border border-gray-300 p-2" onClick={handleCenterClick}><CircleDot /></TooltipTrigger>
                            <TooltipContent>
                                <p>Center</p>
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                </div>
                {graph.Id &&
                    <CytoscapeComponent
                        cy={(cy) => {
                            chartRef.current = cy

                            // Make sure no previous listeners are attached
                            cy.removeAllListeners();

                            // Listen to the click event on nodes for expanding the node
                            cy.on('dbltap', 'node', async function (evt) {
                                var node: Node = evt.target.json().data;
                                let elements = await parmas.onFetchNode(node);
                                cy.add(elements).layout(LAYOUT).run()
                            });
                        }}
                        stylesheet={STYLESHEET}
                        elements={graph.Elements}
                        layout={LAYOUT}
                        className="w-full h-full"
                    />
                }
            </main>
        </>
    )
}