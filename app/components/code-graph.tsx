import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/use-toast";
import CytoscapeComponent from 'react-cytoscapejs'
import { useRef, useState } from "react";
import { Graph, Node } from "./model";
import { RESPOSITORIES } from "./repositories";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ZoomIn, ZoomOut } from "lucide-react";

export function CodeGraph(parmas: { graph: Graph, onFetchGraph: (url: string) => void, onFetchNode: (node: Node) => void }) {

    const [url, setURL] = useState('');
    const chartRef = useRef<cytoscape.Core | null>(null)

    // A function that handles the change event of the url input box
    async function handleRepoInputChange(event: any) {

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

    function onRepoSelected(value: string): void {
        setURL(value)
        parmas.onFetchGraph(url)
    }

    return (
        <>
            <header className="border p-4">
                <form className="flex flex-row gap-2" onSubmit={handleSubmit}>
                    <Select onValueChange={onRepoSelected}>
                        <SelectTrigger className="w-1/3">
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
                    <Input placeholder="Github repo URL" className='border' type="url" onChange={handleRepoInputChange} />
                    <Button type="submit" >Send</Button>
                </form>
            </header>
            <main className="h-full w-full">
                <div className="flex flex-row" >
                    <Button className="text-gray-600 dark:text-gray-400 rounded-lg border border-gray-300" variant="ghost" onClick={() => handleZoomClick(1.1)}><ZoomIn /></Button>
                    <Button className="text-gray-600 dark:text-gray-400 rounded-lg border border-gray-300" variant="ghost" onClick={() => handleZoomClick(0.9)}><ZoomOut /></Button>
                </div>
                {parmas.graph.Id &&
                    <CytoscapeComponent
                        cy={(cy) => {
                            chartRef.current = cy
                            cy.removeAllListeners();

                            cy.on('dbltap', 'node', function (evt) {
                                var node: Node = evt.target.json().data;
                                parmas.onFetchNode(node);
                            });
                        }}
                        stylesheet={[
                            {
                                selector: 'node',
                                style: {
                                    label: "data(name)",
                                    "text-valign": "center",
                                    "text-halign": "center",
                                    shape: "ellipse",
                                    height: 10,
                                    width: 10,
                                    "background-color": "data(color)",
                                    "font-size": "3",
                                },
                            },
                            {
                                selector: "edge",
                                style: {
                                    width: 0.5,
                                    'line-color': '#ccc',
                                    "arrow-scale": 0.3,
                                    "target-arrow-shape": "triangle",
                                    label: "data(label)",
                                    'curve-style': 'straight',
                                    "text-background-color": "#ffffff",
                                    "text-background-opacity": 1,
                                    "font-size": "3",
                                },
                            },
                        ]}
                        elements={parmas.graph.Elements}
                        layout={{
                            name: "cose",
                            fit: true,
                            padding: 30,
                            avoidOverlap: true,
                        }}
                        className="w-full h-full"
                    />
                }
            </main>
        </>
    )
}