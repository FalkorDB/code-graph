import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/use-toast";
import CytoscapeComponent from 'react-cytoscapejs'
import { useRef, useState } from "react";
import { Graph, Node } from "./model";
import { RESPOSITORIES } from "./repositories";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ZoomIn, ZoomOut } from "lucide-react";

export function CodeGraph(parmas: { graph: Graph, setGraph: (graph: Graph) => void }) {

    const [url, setURL] = useState('');

    const chartRef = useRef<cytoscape.Core | null>(null)
    const factor = useRef<number>(1)

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


        sendRepo();
    }

    function sendRepo() {
        let value = url;
        if (!value || value.length === 0) {
            value = 'https://github.com/falkorDB/falkordb-py';
        }

        fetch('/api/repo', {
            method: 'POST',
            body: JSON.stringify({
                url: value
            })
        }).then(async (result) => {
            if (result.status >= 300) {
                throw Error(await result.text())
            }
            return result.json()
        }).then(data => {
            let graph = Graph.create(data);
            parmas.setGraph(graph);
        }).catch((error) => {
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: error.message,
            });
        });
    }

    function handleZoomClick(changefactor: number) {
        factor.current *= changefactor
        let chart = chartRef.current
        if (chart) {
            chart.zoom(chart.zoom() * changefactor)
        }
    }

    function onRepoSelected(value: string): void {
        setURL(value)
        sendRepo()
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

                                fetch(`/api/repo/${parmas.graph.Id}/${node.name}`, {
                                    method: 'GET'
                                }).then(async (result) => {
                                    if (result.status >= 300) {
                                        throw Error(await result.text())
                                    }
                                    return result.json()
                                }).then(data => {
                                    parmas.graph.extend(data)
                                    parmas.setGraph(parmas.graph)
                                }).catch((error) => {
                                    toast({
                                        variant: "destructive",
                                        title: "Uh oh! Something went wrong.",
                                        description: error.message,
                                    })
                                })
                            });
                        }}
                        stylesheet={[
                            {
                                selector: 'node',
                                style: {
                                    label: "data(label)",
                                    "text-valign": "center",
                                    "text-halign": "center",
                                    shape: "ellipse",
                                    height: 10,
                                    width: 10,
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