import { Input } from "@/components/ui/input";
import CytoscapeComponent from 'react-cytoscapejs'
import { useContext, useEffect, useRef, useState } from "react";
import { Category, Node } from "./model";
import { RESPOSITORIES } from "../api/repo/repositories";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { GraphContext } from "./provider";
import cytoscape from 'cytoscape';
import fcose from 'cytoscape-fcose';
import { Toolbar } from "./toolbar";
import { Labels } from "./labels";
import { GitFork, Search } from "lucide-react";

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

    function onRepoSelected(value: string): void {
        setURL(value)
        parmas.onFetchGraph(value)
    }

    // const defaultRepo = RESPOSITORIES[0];
    // // Fetch the default graph on first render
    // useEffect(() => {
    //     onRepoSelected(defaultRepo)
    // }, []);

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
        <div className="h-full w-full flex flex-col gap-4">
            <header className="flex flex-col gap-4">
                <h1 className="text-2xl font-medium">Knowledge Graph</h1>
                <Select onValueChange={onRepoSelected}>
                    <SelectTrigger className="border focus:ring-0 focus:ring-offset-0">
                        <SelectValue placeholder="Select a repo" />
                    </SelectTrigger>
                    <SelectContent>
                        {
                            RESPOSITORIES.map((repo, index) => {
                                return <SelectItem key={index} value={repo}>{repo}</SelectItem>
                            })
                        }
                    </SelectContent>
                </Select>
            </header>
            <main className="grow">
                {graph.Id ?
                    (
                        <>
                            <div className="flex justify-between p-2">
                                <Toolbar className="col-start-1" chartRef={chartRef} />
                                <Labels className="col-start-3 col-end-4" categories={graph.Categories} onClick={onCategoryClick} />
                                <form onSubmit={handleSubmit}>
                                    {
                                        !LIMITED_MODE &&
                                        <div className="relative">
                                            <Input className="border border-black" type="url" onChange={handleRepoInputChange} />
                                            <button className="absolute left-3 top-2" type="submit">
                                                <Search />
                                            </button>
                                        </div>
                                    }
                                </form>
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
                        <div className="flex flex-col items-center justify-center h-full text-gray-400">
                            <GitFork size={100} color="gray" />
                            <h1 className="text-4xl">Select a repo to show its graph here</h1>
                        </div>
                    )
                }
            </main>
        </div>
    )
}