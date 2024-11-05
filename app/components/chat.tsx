import { toast } from "@/components/ui/use-toast";
import { Dispatch, MutableRefObject, SetStateAction, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { AlignLeft, ArrowRight, ChevronDown, Lightbulb, Undo2 } from "lucide-react";
import { Path } from "../page";
import Input from "./Input";
import { Graph } from "./model";
import { cn } from "@/lib/utils";
import { LAYOUT } from "./code-graph";

enum MessageTypes {
    Query,
    Response,
    Tip,
    Path,
    PathResponse,
    Pending,
    Text,
}

interface Message {
    type: MessageTypes;
    text?: string;
    paths?: { nodes: any[], edges: any[] }[];
}

interface Props {
    repo: string
    path: Path | undefined
    setPath: Dispatch<SetStateAction<Path | undefined>>
    graph: Graph
    chartRef: MutableRefObject<cytoscape.Core | null>
    selectedPathId: string | undefined
    isPath: boolean
    setIsPath: (isPathResponse: boolean) => void
}

const RemoveLastPath = (messages: Message[]) => {
    const index = messages.findIndex((m) => m.type === MessageTypes.Path)

    if (index !== -1) {
        messages = [...messages.slice(0, index - 2), ...messages.slice(index + 1)];
        messages = RemoveLastPath(messages)
    }

    return messages
}

export function Chat({ repo, path, setPath, graph, chartRef, selectedPathId, isPath, setIsPath }: Props) {

    // Holds the messages in the chat
    const [messages, setMessages] = useState<Message[]>([{ type: MessageTypes.Tip }]);

    // Holds the messages in the chat
    const [paths, setPaths] = useState<{ nodes: any[], edges: any[] }[]>([]);

    const [selectedPath, setSelectedPath] = useState<{ nodes: any[], edges: any[] }>();

    // Holds the user input while typing
    const [query, setQuery] = useState('');

    const [isPathResponse, setIsPathResponse] = useState(false);

    // A reference to the chat container to allow scrolling to the bottom
    const containerRef: React.RefObject<HTMLDivElement> = useRef(null);

    useEffect(() => {
        const p = paths.find((path) => [...path.edges, ...path.nodes].some((e: any) => e.id === selectedPathId))

        if (!p) return

        handelSetSelectedPath(p)
    }, [selectedPathId])

    useEffect(() => {
        handelSubmit()
    }, [path])

    useEffect(() => {
        if (isPath) return
        setIsPathResponse(false)        
        setSelectedPath(undefined)
        setPaths([])
    }, [isPath])

    useEffect(() => {
        setIsPath(isPathResponse)
    }, [isPathResponse])

    const handelSetSelectedPath = (p: { nodes: any[], edges: any[] }) => {
        const chart = chartRef.current

        if (!chart) return

        setSelectedPath(prev => {
            if (prev) {
                if (isPathResponse && paths.some((path) => [...path.nodes, ...path.edges].every((e: any) => [...prev.nodes, ...prev.edges].some((el: any) => el.id === e.id)))) {
                    chart.edges().forEach(e => {
                        const id = e.id()

                        if (prev.edges.some(el => el.id == id) && !p.edges.some(el => el.id == id)) {
                            e.style({
                                width: 0.5,
                                "line-style": "dashed",
                                "line-color": "#FF66B3",
                                "arrow-scale": 0.3,
                                "target-arrow-color": "#FF66B3",
                            })
                        }
                    })
                } else {
                    const elements = chart.elements().filter(e => [...prev.edges, ...prev.nodes].some(el => el.id == e.id())).removeStyle()
                    if (isPathResponse) {
                        elements.forEach(e => {
                            if (e.isNode()) {
                                e.style({
                                    "border-width": 0.5,
                                    "color": "gray",
                                    "border-color": "black",
                                    "background-color": "gray",
                                    "opacity": 0.5
                                });
                            }

                            if (e.isEdge()) {
                                e.style({
                                    "line-color": "gray",
                                    "target-arrow-color": "gray",
                                    "opacity": 0.5,
                                });
                            }
                        })
                    }
                }
            }
            return p
        })

        if (isPathResponse && paths.some((path) => [...path.nodes, ...path.edges].every((e: any) => [...p.nodes, ...p.edges].some((el: any) => el.id === e.id)))) {
            chart.edges().forEach(e => {
                const id = e.id()

                if (p.edges.some(el => el.id == id)) {
                    e.style({
                        width: 1,
                        "line-style": "solid",
                        "line-color": "#FF66B3",
                        "arrow-scale": 0.6,
                        "target-arrow-color": "#FF66B3",
                    })
                }
            })
            chart.elements().filter(el => [...p.nodes, ...p.edges].some(e => e.id == el.id())).layout(LAYOUT).run();
        } else {
            chart.elements().filter(el => [...p.nodes, ...p.edges].some(e => e.id == el.id())).forEach(el => {
                if (el.id() == p.nodes[0].id || el.id() == p.nodes[p.nodes.length - 1].id) {
                    el.removeStyle().style({
                        "border-width": 1,
                        "border-color": "#FF66B3",
                        "border-opacity": 1,
                    });
                } else if (el.isNode()) {
                    el.removeStyle().style({
                        "border-width": 0.5,
                        "border-color": "#FF66B3",
                        "border-opacity": 1,
                    });
                }
                if (el.isEdge()) {
                    el.removeStyle().style({
                        width: 1,
                        "line-style": "solid",
                        "line-color": "#FF66B3",
                        "arrow-scale": 0.6,
                        "target-arrow-color": "#FF66B3",
                    })
                }
            }).layout(LAYOUT).run();
        }
    }

    // A function that handles the change event of the url input box
    async function handleQueryInputChange(event: any) {

        if (event.key === "Enter") {
            await handleQueryClick(event);
        }

        // Get the new value of the input box
        const value = event.target.value;

        // Update the url state
        setQuery(value);
    }

    // Send the user query to the server
    async function sendQuery(q: string) {
        if (!q) {
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: "Please enter a question.",
            })
            return
        }

        setQuery("")
        setMessages((messages) => [...messages, { text: q, type: MessageTypes.Query }, { text: "", type: MessageTypes.Pending }]);

        containerRef.current?.scrollTo(0, containerRef.current?.scrollHeight);

        const result = await fetch(`/api/chat/${repo}?msg=${encodeURIComponent(q)}`, {
            method: 'POST'
        })

        if (!result.ok) {
            setMessages((prev) => {
                prev = [...prev.slice(0, -1)];
                return [...prev, { type: MessageTypes.Response, text: "Sorry but I couldn't answer your question, please try rephrasing." }];
            });
            return
        }

        const json = await result.json()

        setMessages((prev) => {
            prev = prev.slice(0, -1);
            return [...prev, { text: json.result.response, type: MessageTypes.Response }];
        });
    }

    // A function that handles the click event
    const handleQueryClick = async (event: any) => {
        event.preventDefault();
        return sendQuery(query.trim());
    }

    // Scroll to the bottom of the chat on new message
    useEffect(() => {
        containerRef.current?.scrollTo(0, containerRef.current?.scrollHeight);
    }, [messages]);

    const handelSubmit = async () => {
        setSelectedPath(undefined)

        const chart = chartRef?.current

        if (!chart || !path?.start?.id || !path.end?.id) return

        const result = await fetch(`/api/repo/${repo}/${path.start.id}/?targetId=${path.end.id}`, {
            method: 'POST'
        })

        if (!result.ok) {
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: await result.text(),
            })
            return
        }

        const json = await result.json()

        if (json.result.paths.length === 0) {
            toast({
                title: `No path found`,
                description: `no path found between node ${path.start.name} - ${path.end.name}`,
            })
            return
        }

        const formattedPaths: { nodes: any[], edges: any[] }[] = json.result.paths.map((p: any) => ({ nodes: p.filter((node: any, i: number) => i % 2 === 0), edges: p.filter((edge: any, i: number) => i % 2 !== 0) }))
        chart.add(formattedPaths.flatMap((p: any) => graph.extend(p, false, path)))
        formattedPaths.forEach(p => p.edges.forEach(e => e.id = `_${e.id}`))
        graph.Elements.forEach((element: any) => {
            const { id } = element.data
            const e = chart.elements().filter(el => el.id() == id)
            if (id == path.start?.id || id == path.end?.id) {
                e.style({
                    'border-width': 1,
                    'border-color': '#FF66B3',
                    'border-opacity': 1,
                });
            } else if (formattedPaths.some((p: any) => [...p.nodes, ...p.edges].some((el: any) => el.id == id))) {
                if (e.isNode()) {
                    e.style({
                        'border-width': 0.5,
                        'border-color': '#FF66B3',
                        'border-opacity': 1,
                    });
                }

                if (e.isEdge()) {
                    e.style({
                        "line-style": "dashed",
                        "line-color": "#FF66B3",
                        "target-arrow-color": "#FF66B3",
                        "opacity": 1
                    });
                }
            } else {
                if (e.isNode()) {
                    e.style({
                        "border-width": 0.5,
                        "color": "gray",
                        "border-color": "black",
                        "background-color": "gray",
                        "opacity": 0.5
                    });
                }

                if (e.isEdge()) {
                    e.style({
                        "line-color": "gray",
                        "target-arrow-color": "gray",
                        "opacity": 0.5,
                    });
                }
            }
        })
        const elements = chart.elements().filter((element) => {
            return formattedPaths.some(p => [...p.nodes, ...p.edges].some((node) => node.id == element.id()))
        });
        elements.layout(LAYOUT).run()
        setPaths(formattedPaths)
        setMessages(prev => [...prev.slice(0, -2), { type: MessageTypes.PathResponse, paths: formattedPaths }])
        setPath(undefined)
        setIsPathResponse(true)
    }

    const getMessage = (message: Message, index?: number) => {
        switch (message.type) {
            case MessageTypes.Query: return (
                <div key={index} className="flex flex-col gap-2">
                    <div className="flex gap-2">
                        <AlignLeft />
                        <h1 className="text-lg font-medium">You</h1>
                    </div>
                    <p className="text-warp">{message.text}</p>
                </div>
            )
            case MessageTypes.Response: return (
                <div key={index} className="flex flex-col gap-2">
                    <div className="flex gap-2">
                        <Undo2 className="rotate-180" />
                        <h1 className="text-lg font-medium">Answer</h1>
                    </div>
                    <p className="text-warp">{message.text?.replaceAll('"', "")}</p>
                </div>
            )
            case MessageTypes.Text: return (
                <p key={index} >{message.text}</p>
            )
            case MessageTypes.Path: {
                return (
                    <div className="flex flex-col gap-4" key={index}>
                        <Input
                            parentClassName="w-full"
                            graph={graph}
                            onValueChange={({ name, id }) => setPath(prev => ({ start: { name, id }, end: prev?.end }))}
                            value={path?.start?.name}
                            placeholder="Start typing starting point"
                            type="text"
                            icon={<ChevronDown color="gray" />}
                            node={path?.start}
                            scrollToBottom={() => containerRef.current?.scrollTo(0, containerRef.current?.scrollHeight)}
                        />
                        <Input
                            parentClassName="w-full"
                            graph={graph}
                            value={path?.end?.name}
                            onValueChange={({ name, id }) => setPath(prev => ({ end: { name, id }, start: prev?.start }))}
                            placeholder="Start typing end point"
                            type="text"
                            icon={<ChevronDown color="gray" />}
                            node={path?.end}
                            scrollToBottom={() => containerRef.current?.scrollTo(0, containerRef.current?.scrollHeight)}
                        />
                    </div>
                )
            }
            case MessageTypes.PathResponse: return (
                <div key={index} className="flex flex-col gap-2">
                    {
                        message.paths &&
                        message.paths.map((p, i: number) => (
                            <button
                                key={i}
                                className={cn("flex text-wrap border p-2 gap-2", p.nodes.length === selectedPath?.nodes.length && selectedPath?.nodes.every(node => p?.nodes.some((n) => n.id === node.id)) && "border-[#FF66B3] bg-[#FFF0F7]")}
                                onClick={() => {
                                    handelSetSelectedPath(p)
                                    setIsPath(true)
                                }}
                            >
                                <p className="font-bold">#{i}</p>
                                <div className="flex flex-wrap">
                                    {
                                        p.nodes.map((node: any, j: number) => (
                                            <span key={j} className={cn((j === 0 || j === p.nodes.length - 1) && "font-bold")}>
                                                {` - ${node.properties.name}`}
                                            </span>
                                        ))
                                    }
                                </div>
                            </button>
                        ))
                    }
                </div>
            )
            case MessageTypes.Tip: return (
                <div className="flex flex-col gap-6" key={index}>
                    <button
                        className="flex gap-2 p-4 border bg-gray-100 hover:bg-gray-200 rounded-md"
                    >
                        <Lightbulb />
                        <div className="flex flex-col gap-2 text-start">
                            <h1 className="font-bold">Show unreachable code</h1>
                            <p>Remove it if unnecessary or fix logic issues.</p>
                        </div>
                    </button>
                    <button
                        className="flex gap-2 p-4 border bg-gray-100 hover:bg-gray-200 rounded-md"
                        onClick={() => {
                            setPath({})
                            setMessages(prev => [
                                ...RemoveLastPath(prev),
                                { type: MessageTypes.Query, text: "Create a path" },
                                {
                                    type: MessageTypes.Response,
                                    text: "Please select a starting point and the end point. Select or press relevant item on the graph"
                                },
                                { type: MessageTypes.Path, path }
                            ])
                            if (isPathResponse) {
                                chartRef.current?.elements().removeStyle().layout(LAYOUT).run()
                                setIsPathResponse(false)
                            }
                        }}
                    >
                        <Lightbulb />
                        <div className="flex flex-col gap-2 text-start">
                            <h1 className="font-bold">Show the path</h1>
                            <p>Fetch, update, batch, and navigate data efficiently</p>
                        </div>
                    </button>
                    <button className="flex gap-2 p-4 border bg-gray-100 hover:bg-gray-200 rounded-md">
                        <Lightbulb />
                        <div className="flex flex-col gap-2 text-start">
                            <h1 className="font-bold">Show me cluster</h1>
                            <p>Scale and distribute workloads across multiple servers</p>
                        </div>
                    </button>
                </div>
            )
            default: return (
                <div key={index} className="flex gap-2">
                    <Image src="/dots.gif" width={100} height={10} alt="Waiting for response" />
                </div>
            )
        }
    }

    return (
        <div className="h-full flex flex-col justify-between px-6 pt-10 pb-4 gap-4">
            <main ref={containerRef} className="grow flex flex-col overflow-y-auto gap-6 px-4">
                <h1 className="text-xl font-extrabold">WELCOME TO OUR ASSISTANCE SERVICE</h1>
                <span className="text-gray-500 text-lg">
                    We can help you access and update only the needed
                    data via paths, optimizing network requests with
                    batching and catching for better performance.
                </span>
                {
                    messages.map((message, index) => {
                        return getMessage(message, index)
                    })
                }
            </main>
            <footer>
                {repo &&
                    <div className="flex gap-4 px-4">
                        <button className="p-4 border rounded-md hover:border-[#FF66B3] hover:bg-[#FFF0F7]" onClick={() => setMessages(prev => [...prev, { type: MessageTypes.Tip }])}>
                            <Lightbulb />
                        </button>
                        <form className="grow relative" onSubmit={handleQueryClick}>
                            <input className="w-full p-4 border rounded-md" placeholder="Ask your question" onChange={handleQueryInputChange} value={query} />
                            <button className="absolute bg-gray-200 top-2 right-2 p-2 rounded-md hover:bg-gray-300">
                                <ArrowRight color="white" />
                            </button>
                        </form>
                    </div>
                }
            </footer>
        </div>
    );
}
