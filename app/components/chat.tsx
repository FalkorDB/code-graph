import { toast } from "@/components/ui/use-toast";
import { Dispatch, FormEvent, SetStateAction, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { AlignLeft, ArrowDown, ArrowRight, ChevronDown, Lightbulb, Undo2 } from "lucide-react";
import { Path } from "../page";
import Input from "./Input";
import { Graph, GraphData, Link } from "./model";
import { cn } from "@/lib/utils";
import { TypeAnimation } from "react-type-animation";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { prepareArg } from "../utils";
import { NodeObject, ForceGraphMethods } from "react-force-graph-2d";

type PathData = {
    nodes: any[]
    links: any[]
}

enum MessageTypes {
    Query,
    Response,
    Path,
    PathResponse,
    Pending,
    Text,
}

interface Message {
    type: MessageTypes;
    text?: string;
    paths?: { nodes: any[], links: any[] }[];
    graphName?: string;
}

interface Props {
    repo: string
    path: Path | undefined
    setPath: Dispatch<SetStateAction<Path | undefined>>
    graph: Graph
    selectedPathId: number | undefined
    isPathResponse: boolean | undefined
    setIsPathResponse: (isPathResponse: boolean | undefined) => void
    setData: Dispatch<SetStateAction<GraphData>>
    chartRef: React.MutableRefObject<ForceGraphMethods<Node, Link>>
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

export function Chat({ repo, path, setPath, graph, selectedPathId, isPathResponse, setIsPathResponse, setData, chartRef }: Props) {

    // Holds the messages in the chat
    const [messages, setMessages] = useState<Message[]>([]);

    // Holds the messages in the chat
    const [paths, setPaths] = useState<PathData[]>([]);

    const [selectedPath, setSelectedPath] = useState<PathData>();

    // Holds the user input while typing
    const [query, setQuery] = useState('');

    const [tipOpen, setTipOpen] = useState(false);

    const [sugOpen, setSugOpen] = useState(false);

    // A reference to the chat container to allow scrolling to the bottom
    const containerRef: React.RefObject<HTMLDivElement> = useRef(null);

    const isSendMessage = messages.some(m => m.type === MessageTypes.Pending) || (messages.some(m => m.text === "Please select a starting point and the end point. Select or press relevant item on the graph") && !messages.some(m => m.type === MessageTypes.Path))

    useEffect(() => {
        const p = paths.find((path) => [...path.links, ...path.nodes].some((e: any) => e.id === selectedPathId))

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
        if (isPathResponse || isPathResponse === undefined) return
        setIsPathResponse(false)
        setSelectedPath(undefined)
        setPaths([])
    }, [isPathResponse])

    const handleSetSelectedPath = (p: PathData) => {
        const chart = chartRef.current
        
        if (!chart) return
        setSelectedPath(prev => {
            if (prev) {
                if (isPathResponse && paths.some((path) => [...path.nodes, ...path.links].every((e: any) => [...prev.nodes, ...prev.links].some((e: any) => e.id === e.id)))) {
                    graph.getElements().forEach(link => {
                        const { id } = link

                        if (prev.links.some(e => e.id === id) && !p.links.some(e => e.id === id)) {
                            link.isPathSelected = false
                        }
                    })
                } else {
                    const elements = graph.getElements().filter(e => [...prev.links, ...prev.nodes].some(el => el.id === e.id && ![...p.nodes, ...p.links].some(ele => ele.id === el.id)))
                    if (isPathResponse || isPathResponse === undefined) {
                        elements.forEach(e => {
                            e.isPath = false
                            e.isPathSelected = false
                        })
                    }
                }
            }
            return p
        })
        if (isPathResponse && paths.length > 0 && paths.some((path) => [...path.nodes, ...path.links].every((e: any) => [...p.nodes, ...p.links].some((el: any) => el.id === e.id)))) {
            graph.Elements.links.forEach(e => {
                if (p.links.some(el => el.id === e.id)) {
                    e.isPathSelected = true
                }
            })
        } else {
            const elements: PathData = { nodes: [], links: [] };
            p.nodes.forEach(node => {
                let element = graph.Elements.nodes.find(n => n.id === node.id)
                if (!element) {
                    elements.nodes.push(node)
                }
            })
            p.links.forEach(link => {
                let element = graph.Elements.links.find(l => l.id === link.id)
                if (!element) {
                    elements.links.push(link)
                }
            })
            graph.extend(elements, true, { start: p.nodes[0], end: p.nodes[p.nodes.length - 1] })
            graph.getElements().filter(e => "source" in e ? p.links.some(l => l.id === e.id) : p.nodes.some(n => n.id === e.id)).forEach(e => {
                if ((e.id === p.nodes[0].id || e.id === p.nodes[p.nodes.length - 1].id) || "source" in e) {
                    e.isPathSelected = true
                } else {
                    e.isPath = true
                }
            });
        }
        setData({ ...graph.Elements })
        setTimeout(() => {
            chart.zoomToFit(1000, 150, (n: NodeObject<Node>) => p.nodes.some(node => node.id === n.id));
        }, 0)
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
        const chart = chartRef.current

        if (!chart) return

        setSelectedPath(undefined)

        if (!path?.start?.id || !path.end?.id) return

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

        const formattedPaths: PathData[] = json.result.paths.map((p: any) => ({ nodes: p.filter((n: any, i: number) => i % 2 === 0), links: p.filter((l: any, i: number) => i % 2 !== 0) }))
        formattedPaths.forEach((p: any) => graph.extend(p, false, path))

        setPaths(formattedPaths)
        setMessages((prev) => [...RemoveLastPath(prev), { type: MessageTypes.PathResponse, paths: formattedPaths, graphName: graph.Id }]);
        setPath(undefined)
        setIsPathResponse(true)
        setData({ ...graph.Elements })
        setTimeout(() => {
            chart.zoomToFit(1000, 150, (n: NodeObject<Node>) => formattedPaths.some(p => p.nodes.some(node => node.id === n.id)));
        }, 0)
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
                        setIsPathResponse(false)
                        graph.getElements().forEach(e => {
                            e.isPath = false
                            e.isPathSelected = false
                        })
                    }

                    setTimeout(() => setMessages(prev => [...prev, {
                        type: MessageTypes.Response,
                        text: "Please select a starting point and the end point. Select or press relevant item on the graph"
                    }]), 300)
                    setTimeout(() => {
                        setMessages(prev => [...prev, { type: MessageTypes.Path }])
                        setPath({})
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
                            value={path?.start?.name || ""}
                            placeholder="Start typing starting point"
                            type="text"
                            icon={<ChevronDown color="gray" />}
                            node={path?.start}
                            scrollToBottom={() => containerRef.current?.scrollTo(0, containerRef.current?.scrollHeight)}
                        />
                        <Input
                            parentClassName="w-full"
                            graph={graph}
                            value={path?.end?.name || ""}
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
                                    selectedPath?.nodes.every(node => p?.nodes.some((n) => n.id === node.id)) &&
                                    "border-[#ffde21] bg-[#ffde2133]",
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

                                    if (selectedPath?.nodes.every(node => p?.nodes.some((n) => n.id === node.id)) && selectedPath.nodes.length === p.nodes.length) return
                                    
                                    if (!isPathResponse) {
                                        setIsPathResponse(undefined)
                                    
                                    }
                                    handleSetSelectedPath(p)
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
                                    <button data-name="questionOptionsMenu" className="bg-gray-200 p-2 rounded-md hover:bg-gray-300">
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
