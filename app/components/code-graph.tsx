import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import CytoscapeComponent from 'react-cytoscapejs'
import { useContext, useEffect, useRef, useState } from "react";
import { Category, Node, getCategoryColors } from "./model";
import { RESPOSITORIES } from "../api/repo/repositories";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CircleDot, ZoomIn, ZoomOut } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Chat } from "./chat";
import { GraphContext } from "./provider";

import cytoscape from 'cytoscape';
import fcose from 'cytoscape-fcose';
import { Skeleton } from "@/components/ui/skeleton";
import { Toolbar } from "./toolbar";
import { Labels } from "./labels";

const LIMITED_MODE = process.env.NEXT_PUBLIC_MODE?.toLowerCase() === 'limited';

// The stylesheet for the graph
const STYLESHEET: cytoscape.Stylesheet[] = [
    {
        selector: "core",
        style: {
            'active-bg-size': 0,  // hide gray circle when panning
            // All of the following styles are meaningless and are specified
            // to satisfy the linter...
            'active-bg-color': 'blue',
            'active-bg-opacity': 0.3,
            "selection-box-border-color": 'blue',
            "selection-box-border-width": 0,
            "selection-box-opacity": 1,
            "selection-box-color": 'blue',
            "outside-texture-bg-color": 'blue',
            "outside-texture-bg-opacity": 1,
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


cytoscape.use(fcose);

const LAYOUT = {
    name: "fcose",
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
        parmas.onFetchGraph(value)
    }

    const defaultRepo = RESPOSITORIES[0];
    // Fetch the default graph on first render
    useEffect(() => {
        onRepoSelected(defaultRepo)
    }, []);

    function onCategoryClick(category: Category) {
        let chart = chartRef.current
        if (chart) {
            let elements = chart.elements(`node[category = "${category.name}"]`)
            category.show = !category.show

            if (category.show) {
                elements.style({ display: 'element' })
            } else {
                elements.style({ display: 'none' })
            }
            chart.elements().layout(LAYOUT).run();
        }
    }

    return (
        <>
            <header className="border p-4">
                <form className="flex flex-row gap-2" onSubmit={handleSubmit}>
                    <Select onValueChange={onRepoSelected} defaultValue={defaultRepo}>
                        <SelectTrigger className={LIMITED_MODE ? "border" : "border w-2/3"}>
                            <SelectValue placeholder="Suggested repositories" />
                        </SelectTrigger>
                        <SelectContent>
                            {
                                RESPOSITORIES.map((repo, index) => {
                                    return <SelectItem key={index} value={repo}>{repo}</SelectItem>
                                })
                            }
                        </SelectContent>
                    </Select>
                    {
                        !LIMITED_MODE &&
                        <>
                            <Input placeholder="Github repo URL" className="border" type="url" onChange={handleRepoInputChange} />
                            <Button type="submit">Send</Button>
                        </>
                    }
                </form>
            </header>
            <main className="h-full w-full">
                {graph.Id ?
                    (
                        <>
                            <div className="grid grid-cols-6 gap-4 p-2">
                                <Toolbar className="col-start-1" chartRef={chartRef} />
                                <Labels className="col-start-3 col-end-4" categories={graph.Categories} onClick={onCategoryClick}/>
                            </div>

                            <CytoscapeComponent
                                cy={(cy) => {
                                    chartRef.current = cy

                                    // Make sure no previous listeners are attached
                                    cy.removeAllListeners();

                                    // Listen to the click event on nodes for expanding the node
                                    cy.on('dbltap', 'node', async function (evt) {
                                        var node: Node = evt.target.json().data;
                                        let elements = await parmas.onFetchNode(node);
                                        //cy.add(elements).layout(LAYOUT).run()

                                        // adjust entire graph.
                                        if (elements.length > 0) {
                                            cy.add(elements);
                                            cy.elements().layout(LAYOUT).run();
                                        }
                                    });
                                }}
                                stylesheet={STYLESHEET}
                                elements={graph.Elements}
                                layout={LAYOUT}
                                className="w-full h-full"
                            />
                        </>
                    ) :
                    (
                        <div className="flex flex-col items-center justify-center h-full space-y-4">
                            <div className="text-gray-600 text-4xl ">
                                Loading Repository Graph...
                            </div>
                            <div className="flex items-center justify-center space-x-4">
                                <Skeleton className="h-12 w-12 rounded-full bg-gray-600" />
                                <div className="space-y-2">
                                    <Skeleton className="h-4 w-[250px] bg-gray-600" />
                                    <Skeleton className="h-4 w-[200px] bg-gray-600" />
                                </div>
                            </div>
                        </div>
                    )
                }
            </main>
        </>
    )
}