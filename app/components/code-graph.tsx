import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/use-toast";
import ReactECharts, { EChartsInstance } from 'echarts-for-react';
import { useRef, useState } from "react";
import { Graph } from "./model";
import { RESPOSITORIES } from "./repositories";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function CodeGraph(parmas: { graph: Graph, setGraph: (graph: Graph) => void }) {

    const [url, setURL] = useState('');

    const echartRef = useRef<EChartsInstance | null>(null)
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
        let chart = echartRef.current
        if (chart) {
            let options = getOptions(parmas.graph)
            chart.setOption(options)
        }
    }

    function getOptions(graph: Graph) {
        const currentFactor = factor.current
        return {
            name: graph.Id,
            tooltip: {
                position: 'right',
            },
            legend: [
                {
                    data: graph.Categories.map(function (c) {
                        return c.name;
                    })
                }
            ],
            toolbox: {
                show: true,
                feature: {
                    // Shows zoom in and zoom out custom buttons
                    myZoomIn: {
                        show: true,
                        title: 'Zoom In',
                        icon: 'path://M19 11 C19 15.41 15.41 19 11 19 6.58 19 3 15.41 3 11 3 6.58 6.58 3 11 3 15.41 3 19 6.58 19 11 zM21 21 C19.55 19.55 18.09 18.09 16.64 16.64 M11 8 C11 10 11 12 11 14 M8 11 C10 11 12 11 14 11',
                        onclick: function () {
                            handleZoomClick(1.1)
                        }
                    },
                    myZoomOut: {
                        show: true,
                        title: 'Zoom Out',
                        icon: 'path://M19 11 C19 15.41 15.41 19 11 19 6.58 19 3 15.41 3 11 3 6.58 6.58 3 11 3 15.41 3 19 6.58 19 11 zM21 21 C19.55 19.55 18.09 18.09 16.64 16.64 M8 11 C10 11 12 11 14 11',
                        onclick: function () {
                            handleZoomClick(0.9)
                        }
                    },
                    restore: {},
                    saveAsImage: {},
                }
            },
            series: [{
                type: 'graph',
                layout: 'force',
                animation: false,
                label: {
                    show: true,
                    position: 'inside',
                    fontSize: 2 * currentFactor
                },
                symbolSize: 10,
                edgeSymbol: ['none', 'arrow'],
                edgeSymbolSize: 0.8 * currentFactor,
                draggable: true,
                nodes: graph.Nodes,
                edges: graph.Edges,
                categories: graph.Categories,
                force: {
                    repulsion: 100,
                },
                edgeLabel: {
                    fontSize: 2 * currentFactor
                },
                roam: true,
                autoCurveness: true,
                lineStyle: {
                    width: 0.3 * currentFactor,
                    opacity: 0.7
                },
                zoom: currentFactor
            }]
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
            <main className="h-full">
                <ReactECharts
                    option={getOptions(parmas.graph)}
                    style={{ height: '100%', width: '100%' }}
                    onChartReady={(e) => {
                        echartRef.current = e
                    }}
                    onEvents={{
                        graphRoam: (params: any) => {
                            if (params.zoom) {
                                handleZoomClick(params.zoom)
                            }
                        },
                        dblclick: async (params: any) => {

                            let value = params?.data?.value;
                            if (!value) {
                                return
                            }
                            let node = JSON.parse(value)

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
                        }
                    }}
                />
            </main>
        </>
    )
}