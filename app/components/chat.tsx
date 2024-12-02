import { toast } from "@/components/ui/use-toast";
import { Dispatch, FormEvent, MutableRefObject, SetStateAction, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { AlignLeft, ArrowDown, ArrowRight, ChevronDown, Lightbulb, Undo2 } from "lucide-react";
import { Path } from "../page";
import Input from "./Input";
import { Graph } from "./model";
import { cn } from "@/lib/utils";
import { LAYOUT } from "./code-graph";
import { TypeAnimation } from "react-type-animation";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import cytoscape from "cytoscape";
import { prepareArg } from "../utils";

enum MessageTypes {
    Query,
    Response,
    Path,
    PathResponse,
    Pending,
    Text,
}

const EDGE_STYLE = {
    "line-color": "gray",
    "target-arrow-color": "gray",
    "opacity": 0.5,
}


const PATH_EDGE_STYLE = {
    width: 0.5,
    "line-style": "dashed",
    "line-color": "#FF66B3",
    "arrow-scale": 0.3,
    "target-arrow-color": "#FF66B3",
    "opacity": 1
}

const SELECTED_PATH_EDGE_STYLE = {
    width: 1,
    "line-style": "solid",
    "line-color": "#FF66B3",
    "arrow-scale": 0.6,
    "target-arrow-color": "#FF66B3",
};

const NODE_STYLE = {
    "border-width": 0.5,
    "color": "gray",
    "border-color": "black",
    "background-color": "gray",
    "opacity": 0.5
}

const PATH_NODE_STYLE = {
    "border-width": 0.5,
    "border-color": "#FF66B3",
    "border-opacity": 1,
}

const SELECTED_PATH_NODE_STYLE = {
    "border-width": 1,
    "border-color": "#FF66B3",
    "border-opacity": 1,
};

interface Message {
    type: MessageTypes;
    text?: string;
    paths?: { nodes: any[], edges: any[] }[];
    graphName?: string;
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

const SUGGESTIONS = [
    "List a few recursive functions",
    "What is the name of the most used method?",
    "Who is calling the most used method?",
    "Which function has the largest number of arguments? List a few arguments",
    "Show a calling path between the drop_edge_range_index function and _query, only return function(s) names",
]

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
    const [messages, setMessages] = useState<Message[]>([]);

    // Holds the messages in the chat
    const [paths, setPaths] = useState<{ nodes: any[], edges: any[] }[]>([]);

    const [selectedPath, setSelectedPath] = useState<{ nodes: any[], edges: any[] }>();

    // Holds the user input while typing
    const [query, setQuery] = useState('');

    const [isPathResponse, setIsPathResponse] = useState(false);

    const [tipOpen, setTipOpen] = useState(false);

    const [sugOpen, setSugOpen] = useState(false);

    // A reference to the chat container to allow scrolling to the bottom
    const containerRef: React.RefObject<HTMLDivElement> = useRef(null);

    const isSendMessage = messages.some(m => m.type === MessageTypes.Pending) || (messages.some(m => m.text === "Please select a starting point and the end point. Select or press relevant item on the graph") && !messages.some(m => m.type === MessageTypes.Path))

    useEffect(() => {
        setSelectedPath(undefined)
        setIsPathResponse(false)
    }, [graph.Id])

    useEffect(() => {
        const p = paths.find((path) => [...path.edges, ...path.nodes].some((e: any) => e.id === selectedPathId))

        if (!p) return

        handleSetSelectedPath(p)
    }, [selectedPathId])

    // Scroll to the bottom of the chat on new message
    useEffect(() => {
        setTimeout(() => {
            containerRef.current?.scrollTo(0, containerRef.current?.scrollHeight);
        }, 300)
    }, [messages]);

    useEffect(() => {
        handleSubmit()
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

    const updatePreviousPath = (chart: cytoscape.Core, p: { nodes: any[], edges: any[] }) => {
        setSelectedPath(prev => {
            if (prev) {
                if (isPathResponse && paths.some((path) => [...path.nodes, ...path.edges].every((e: any) => [...prev.nodes, ...prev.edges].some((el: any) => el.id === e.id)))) {
                    chart.edges().forEach(e => {
                        const id = e.id()

                        if (prev.edges.some(el => el.id == id) && !p.edges.some(el => el.id == id)) {
                            e.style(PATH_EDGE_STYLE)
                        }
                    })
                } else {
                    const elements = chart.elements().filter(e => [...prev.edges, ...prev.nodes].some(el => el.id == e.id() && ![...p.nodes, ...p.edges].some(ele => ele.id == e.id()))).removeStyle()
                    if (isPathResponse) {
                        elements.forEach(e => {
                            if (e.isNode()) {
                                e.style(NODE_STYLE);
                            }

                            if (e.isEdge()) {
                                e.style(EDGE_STYLE);
                            }
                        })
                    }
                }
            }
            return p
        })
    }

    const handleSetSelectedPath = (p: { nodes: any[], edges: any[] }) => {
        const chart = chartRef.current

        if (!chart) return

        updatePreviousPath(chart, p)

        if (isPathResponse && paths.some((path) => [...path.nodes, ...path.edges].every((e: any) => [...p.nodes, ...p.edges].some((el: any) => el.id === e.id)))) {
            chart.edges().forEach(e => {
                const id = e.id()

                if (p.edges.some(el => el.id == id)) {
                    e.style(SELECTED_PATH_EDGE_STYLE)
                }
            })
            chart.elements().filter(el => [...p.nodes, ...p.edges].some(e => e.id == el.id())).layout(LAYOUT).run();
        } else {
            const elements: any = { nodes: [], edges: [] };

            [...p.nodes, ...p.edges].forEach(e => {
                let element = chart.elements(`#${e.id}`)
                if (element.length === 0) {
                    debugger
                    const type = "src_node" in e
                    e = type ? { ...e, id: e.id.slice(1) } : e
                    type
                        ? elements.edges.push(e)
                        : elements.nodes.push(e)
                }
            })

            chart.add(graph.extend(elements))
            chart.elements().filter((e) => [...p.nodes, ...p.edges].some((el) => el.id == e.id())).forEach((e) => {
                if (e.id() == p.nodes[0].id || e.id() == p.nodes[p.nodes.length - 1].id) {
                    e.removeStyle().style(SELECTED_PATH_NODE_STYLE);
                } else if (e.isNode()) {
                    e.removeStyle().style(PATH_NODE_STYLE);
                }
                if (e.isEdge()) {
                    e.removeStyle().style(SELECTED_PATH_EDGE_STYLE);
                }
            }).layout(LAYOUT).run();
        }
    }

    // A function that handles the change event of the url input box
    async function handleQueryInputChange(event: any) {

        // Get the new value of the input box
        const value = event.target.value;

        // Update the url state
        setQuery(value);
    }

    // Send the user query to the server
    async function sendQuery(event?: FormEvent, sugQuery?: string) {

        event?.preventDefault();

        if (isSendMessage) return

        const q = query?.trim() || sugQuery!

        if (!q) {
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: "Please enter a question.",
            })
            return
        }

        setQuery("")

        setMessages((messages) => [...messages, { text: q, type: MessageTypes.Query }, { type: MessageTypes.Pending }]);

        const result = await fetch(`/api/chat/${prepareArg(repo)}?msg=${prepareArg(q)}`, {
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

    const handleSubmit = async () => {
        setSelectedPath(undefined)

        const chart = chartRef?.current

        if (!chart || !path?.start?.id || !path.end?.id) return

        const result = await fetch(`/api/repo/${prepareArg(repo)}/${prepareArg(String(path.start.id))}/?targetId=${prepareArg(String(path.end.id))}`, {
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
                e.style(SELECTED_PATH_NODE_STYLE);
            } else if (formattedPaths.some((p: any) => [...p.nodes, ...p.edges].some((el: any) => el.id == id))) {
                if (e.isNode()) {
                    e.style(PATH_NODE_STYLE);
                }

                if (e.isEdge()) {
                    e.style(PATH_EDGE_STYLE);
                }
            } else {
                if (e.isNode()) {
                    e.style(NODE_STYLE);
                }

                if (e.isEdge()) {
                    e.style(EDGE_STYLE);
                }
            }
        })
        const elements = chart.elements().filter((element) => {
            return formattedPaths.some(p => [...p.nodes, ...p.edges].some((node) => node.id == element.id()))
        });
        elements.layout(LAYOUT).run()
        setPaths(formattedPaths)
        setMessages((prev) => [...RemoveLastPath(prev), { type: MessageTypes.PathResponse, paths: formattedPaths, graphName: graph.Id }]);
        setPath(undefined)
        setIsPathResponse(true)
    }

    const getTip = (disabled = false) =>
        <>
            <button
                disabled={disabled}
                className="Tip"
                onClick={() => {
                    setTipOpen(false)
                    setMessages(prev => [
                        ...RemoveLastPath(prev),
                        { type: MessageTypes.Query, text: "Create a path" },
                    ])

                    if (isPathResponse) {
                        chartRef.current?.elements().removeStyle().layout(LAYOUT).run()
                        setIsPathResponse(false)
                    }

                    setTimeout(() => setMessages(prev => [...prev, {
                        type: MessageTypes.Response,
                        text: "Please select a starting point and the end point. Select or press relevant item on the graph"
                    }]), 300)
                    setTimeout(() => {
                        setPath({})
                        setMessages(prev => [...prev, { type: MessageTypes.Path }])
                    }, 4000)
                }}
            >
                <Lightbulb />
                <div>
                    <h1 className="label">Show the path</h1>
                    <p className="text">Fetch, update, batch, and navigate data efficiently</p>
                </div>
            </button>
        </>

    const getMessage = (message: Message, index?: number) => {
        switch (message.type) {
            case MessageTypes.Query: return (
                <div key={index} className="flex flex-col gap-2">
                    <div className="flex gap-2">
                        <AlignLeft />
                        <h1 className="text-lg font-medium">You</h1>
                    </div>
                    <p className="break-words whitespace-pre-wrap">{message.text}</p>
                </div>
            )
            case MessageTypes.Response: return (
                <div key={index} className="flex flex-col gap-2">
                    <div className="flex gap-2">
                        <Undo2 className="rotate-180" />
                        <h1 className="text-lg font-medium break-words whitespace-pre-wrap">Answer</h1>
                    </div>
                    <TypeAnimation
                        key={message.text}
                        sequence={[message.text!]}
                        speed={60}
                        wrapper="span"
                        cursor={false}
                    />
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
                                className={cn(
                                    "flex text-wrap border p-2 gap-2 rounded-md",
                                    p.nodes.length === selectedPath?.nodes.length &&
                                    selectedPath?.nodes.every(node => p?.nodes.some((n) => n.id === node.id)) && "border-[#FF66B3] bg-[#FFF0F7]",
                                    message.graphName !== graph.Id && "opacity-50 bg-gray-200"
                                )}
                                title={message.graphName !== graph.Id ? `Move to graph ${message.graphName} to use this path` : undefined}
                                disabled={message.graphName !== graph.Id}
                                onClick={() => {
                                    if (message.graphName !== graph.Id) {
                                        toast({
                                            title: "Path Disabled",
                                            description: "The path is disabled because it is not from this graph.",
                                        });
                                        return;
                                    }
                                    if (p.nodes.length === selectedPath?.nodes.length &&
                                        selectedPath?.nodes.every(node => p?.nodes.some((n) => n.id === node.id))) return;
                                    handleSetSelectedPath(p);
                                    setIsPath(true);
                                }}
                            >
                                <p className="font-bold">#{i + 1}</p>
                                <div className="flex flex-wrap">
                                    {p.nodes.map((node: any, j: number) => (
                                        <span key={j} className={cn((j === 0 || j === p.nodes.length - 1) && "font-bold")}>
                                            {` - ${node.properties.name}`}
                                        </span>
                                    ))}
                                </div>
                            </button>
                        ))
                    }
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
        <div className="relative h-full flex flex-col justify-between px-6 pt-10 pb-4 gap-4">
            <main data-name="main-chat" ref={containerRef} className="grow flex flex-col overflow-y-auto gap-6 px-4">
                {
                    messages.length === 0 &&
                    <>
                        <h1 className="font-oswald text-[20px] font-semibold leading-[32px] text-left text-[#13343B]">WELCOME TO OUR ASSISTANCE SERVICE</h1>
                        <span className="text-base font-normal leading-5 text-left text-[#7D7D7D]">
                            We can help you access and update only the needed
                            data via paths, optimizing network requests with
                            batching and catching for better performance.
                        </span>
                        {getTip()}
                    </>
                }
                {
                    messages.map((message, index) => {
                        return getMessage(message, index)
                    })
                }
                {
                    tipOpen &&
                    <div ref={ref => ref?.focus()} className="bg-white absolute bottom-24 border rounded-md flex flex-col gap-3 p-2 overflow-y-auto" tabIndex={-1} onMouseDown={(e) => e.preventDefault()} onBlur={() => setTipOpen(false)}>
                        {getTip(isSendMessage)}
                    </div>
                }
            </main>
            <DropdownMenu open={sugOpen} onOpenChange={setSugOpen}>
                <footer>
                    {
                        repo &&
                        <div className="flex gap-4 px-4">
                            <button data-name="lightbulb" onClick={() => setTipOpen(true)} className="p-4 border rounded-md hover:border-[#FF66B3] hover:bg-[#FFF0F7]">
                                <Lightbulb />
                            </button>
                            <form className="grow flex items-center border rounded-md px-2" onSubmit={sendQuery}>
                                <DropdownMenuTrigger asChild>
                                    <button className="bg-gray-200 p-2 rounded-md hover:bg-gray-300">
                                        <ArrowDown color="white" />
                                    </button>
                                </DropdownMenuTrigger>
                                <input className="grow p-4 rounded-md focus-visible:outline-none" placeholder="Ask your question" onChange={handleQueryInputChange} value={query} />
                                <button disabled={isSendMessage} className={`bg-gray-200 p-2 rounded-md ${!isSendMessage && 'hover:bg-gray-300'}`}>
                                    <ArrowRight color="white" />
                                </button>
                            </form>
                        </div>
                    }
                </footer>
                <DropdownMenuContent className="flex flex-col mb-4 w-[20dvw]" side="top">
                    {
                        SUGGESTIONS.map((s, i) => (
                            <button
                                disabled={isSendMessage}
                                type="submit"
                                key={i}
                                className="p-2 text-left hover:bg-gray-200"
                                onClick={() => {
                                    sendQuery(undefined, s)
                                    setSugOpen(false)
                                }}
                            >
                                {s}
                            </button>
                        ))
                    }
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    );
}
