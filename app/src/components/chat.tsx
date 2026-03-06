import { toast } from "@/components/ui/use-toast";
import { Dispatch, FormEvent, SetStateAction, useEffect, useRef, useState } from "react";
import { AlignLeft, ArrowRight, ChevronDown, Lightbulb, Undo2 } from "lucide-react";
import { Message, MessageTypes, Path, PathData, PATH_COLOR } from "@/lib/utils";
import Input from "./Input";
import { Graph, GraphData, Node } from "./model";
import { cn, GraphRef } from "@/lib/utils";
import { TypeAnimation } from "react-type-animation";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

const AUTH_HEADERS: HeadersInit = import.meta.env.VITE_SECRET_TOKEN
  ? { 'Authorization': `Bearer ${import.meta.env.VITE_SECRET_TOKEN}` }
  : {};
import { dataToGraphData, GraphLink, GraphNode } from "@falkordb/canvas";

interface Props {
    repo: string
    path: Path | undefined
    setPath: Dispatch<SetStateAction<Path | undefined>>
    graph: Graph
    selectedPathId: number | undefined
    isPathResponse: boolean | undefined
    setIsPathResponse: (isPathResponse: boolean | undefined) => void
    canvasRef: GraphRef
    messages: Message[]
    setMessages: Dispatch<SetStateAction<Message[]>>
    query: string
    setQuery: Dispatch<SetStateAction<string>>
    selectedPath: PathData | undefined
    setSelectedPath: Dispatch<SetStateAction<PathData | undefined>>
    setCooldownTicks: Dispatch<SetStateAction<number | undefined>>
    setChatOpen?: Dispatch<SetStateAction<boolean>>
    paths: PathData[]
    setPaths: Dispatch<SetStateAction<PathData[]>>
}

const SUGGESTIONS = [
    "List a few recursive functions",
    "What is the name of the most used method?",
    "Who is calling the most used method?",
    "Which function has the largest number of arguments? List a few arguments",
    "Show a calling path between the drop_edge_range_index function and _query, only return function(s) names",
]

type RemoveLastPathResult = {
    messages: Message[]
    insertIndex: number
}

const RemoveLastPath = (messages: Message[]): RemoveLastPathResult => {
    // Find the last Path message so we know where the user was in the conversation
    const index = messages.findLastIndex((m) => m.type === MessageTypes.Path)

    if (index === -1) {
        return { messages, insertIndex: messages.length }
    }

    const groupStart = Math.max(0, index - 2)
    const hasMessagesAfter = index < messages.length - 1
    const cleaned = [...messages.slice(0, groupStart), ...messages.slice(index + 1)]

    // Recurse to strip any remaining Path groups
    const { messages: finalMessages } = RemoveLastPath(cleaned)

    // If there were messages after the Path group, inject the answer there;
    // otherwise just append at the end
    const insertIndex = hasMessagesAfter ? groupStart : finalMessages.length

    return { messages: finalMessages, insertIndex }
}

export function Chat({ messages, setMessages, query, setQuery, selectedPath, setSelectedPath, setChatOpen, repo, path, setPath, graph, selectedPathId, isPathResponse, setIsPathResponse, setCooldownTicks, canvasRef, paths, setPaths }: Props) {

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
        if (messages.length === 0) return
        const timeout = setTimeout(() => {
            containerRef.current?.scrollTo(0, containerRef.current?.scrollHeight);
        }, 300)

        return () => {
            clearTimeout(timeout)
        }
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
        const canvas = canvasRef.current

        if (!canvas) return

        // Sets for the new path
        const pNodeIds = new Set<number>(p.nodes.map((n: Node) => n.id))
        const pLinkIds = new Set<number>(p.links.map((l: any) => l.id))
        const pIds = new Set<number>([...pNodeIds, ...pLinkIds])
        const firstNodeId = p.nodes[0].id
        const lastNodeId = p.nodes[p.nodes.length - 1].id

        // Sets for the previous path (selectedPath is the current value from props)
        const prevNodeIds = new Set<number>((selectedPath?.nodes ?? []).map((n: any) => n.id))
        const prevLinkIds = new Set<number>((selectedPath?.links ?? []).map((e: any) => e.id))
        const prevIds = new Set<number>([...prevNodeIds, ...prevLinkIds])

        // --- Unset previous path on graph elements ---
        if (selectedPath) {
            const pathAlreadyInPrev = isPathResponse && paths.some(path =>
                [...path.nodes, ...path.links].every((e: any) => prevIds.has(e.id))
            )

            if (pathAlreadyInPrev) {
                graph.getElements().forEach((element: any) => {
                    if (prevLinkIds.has(element.id) && !pLinkIds.has(element.id)) {
                        element.isPathSelected = false
                    }
                })
            } else {
                const staleElements = graph.getElements().filter((e: any) => prevIds.has(e.id) && !pIds.has(e.id))
                staleElements.forEach((e: any) => {
                    e.isPath = false
                    e.isPathSelected = false
                    if ("source" in e) {
                        e.color = "#999999"
                    }
                })
            }
        }

        setSelectedPath(p)

        // --- Set new path on graph elements ---
        if (isPathResponse && paths.length > 0 && paths.some(path =>
            [...path.nodes, ...path.links].every((e: any) => pIds.has(e.id))
        )) {
            graph.Elements.links.forEach((e: any) => {
                if (pLinkIds.has(e.id)) {
                    e.isPathSelected = true
                }
            })
        } else {
            const existingNodeIds = new Set<number>(graph.Elements.nodes.map((n: any) => n.id))
            const existingLinkIds = new Set<number>(graph.Elements.links.map((l: any) => l.id))
            const elements: PathData = {
                nodes: p.nodes.filter(node => !existingNodeIds.has(node.id)),
                links: p.links.filter(link => !existingLinkIds.has(link.id)),
            }
            graph.extend(elements, true, { start: p.nodes[0], end: p.nodes[p.nodes.length - 1] })
            graph.getElements()
                .filter((e: any) => "source" in e ? pLinkIds.has(e.id) : pNodeIds.has(e.id))
                .forEach((e: any) => {
                    if (e.id === firstNodeId || e.id === lastNodeId || "source" in e) {
                        e.isPathSelected = true
                    } else {
                        e.isPath = true
                    }
                })
        }

        const currentData = canvas.getGraphData();

        // --- Unset canvas data for previous path elements no longer in the new path ---
        if (selectedPath) {
            currentData.nodes.forEach((n: any) => {
                if (prevNodeIds.has(n.id) && !pNodeIds.has(n.id)) {
                    if (isPathResponse) {
                        // keep isPath + PATH_COLOR border, just deselect
                        n.data.isPathSelected = false
                    } else {
                        n.data.isPath = false
                        n.data.isPathSelected = false
                    }
                }
            })
            currentData.links.forEach((l: any) => {
                if (prevLinkIds.has(l.id) && !pLinkIds.has(l.id)) {
                    if (isPathResponse) {
                        // keep color + dashed path line, just deselect
                        l.data.isPathSelected = false
                    } else {
                        l.data.isPathSelected = false
                        l.color = "#999999"
                    }
                }
            })
        }

        // --- Set canvas data for new path elements ---
        currentData.nodes.forEach((n: any) => {
            if (pNodeIds.has(n.id)) {
                if (n.id === firstNodeId || n.id === lastNodeId) {
                    n.data.isPathSelected = true;
                } else {
                    n.data.isPath = true;
                }
            }
        });
        currentData.links.forEach((l: any) => {
            if (pLinkIds.has(l.id)) {
                l.data.isPathSelected = true;
                l.color = PATH_COLOR;
            }
        });

        canvas.setGraphData(currentData)

        setTimeout(() => {
            canvas.zoomToFit(2, (n: GraphNode) => pNodeIds.has(n.id));
        }, 0)
        setChatOpen && setChatOpen(false)
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

        const result = await fetch(`/api/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...AUTH_HEADERS,
            },
            body: JSON.stringify({ repo: repo, msg: q }),
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
        const canvas = canvasRef.current

        if (!canvas) return

        setSelectedPath(undefined)

        if (!path?.start?.id || !path.end?.id) return

        const pathMessage = [{
            type: MessageTypes.Response,
            text: "Please select a starting point and the end point. Select or press relevant item on the graph"
        }, { type: MessageTypes.Path }]

        setPath(undefined)
        let insertIndex = 0
        setMessages((prev) => {
            const { messages, insertIndex: idx } = RemoveLastPath(prev)
            insertIndex = idx
            const pending: Message = { type: MessageTypes.Pending }
            return [...messages.slice(0, insertIndex), pending, ...messages.slice(insertIndex)]
        })

        const result = await fetch(`/api/find_paths`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...AUTH_HEADERS,
            },
            body: JSON.stringify({ repo: repo, src: String(path.start.id), dest: String(path.end.id) }),
        })

        if (!result.ok) {
            setMessages((prev) => [
                ...prev.slice(0, insertIndex),
                ...pathMessage,
                ...prev.slice(insertIndex + 1),
            ])
            setPath({})
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: await result.text(),
            })
            return
        }

        const json = await result.json()

        if (json.result.paths.length === 0) {
            setMessages((prev) => [
                ...prev.slice(0, insertIndex),
                ...pathMessage,
                ...prev.slice(insertIndex + 1),
            ])
            setPath({})
            toast({
                title: `No path found`,
                description: `no path found between node ${path.start.name} - ${path.end.name}`,
            })
            return
        }

        const formattedPaths: PathData[] = json.result.paths.map((p: any) => ({ nodes: p.filter((_n: any, i: number) => i % 2 === 0), links: p.filter((l: any, i: number) => i % 2 !== 0) }))
        const elements = formattedPaths.reduce<GraphData>(
            (acc, p) => {
                const el = graph.extend(p, false, path)
                acc.nodes.push(...el.nodes)
                acc.links.push(...el.links)
                return acc
            },
            { nodes: [], links: [] }
        )
        setPaths(formattedPaths)
        setMessages((prev) => [
            ...prev.slice(0, insertIndex),
            { type: MessageTypes.PathResponse, paths: formattedPaths, graphName: graph.Id },
            ...prev.slice(insertIndex + 1),
        ]);
        setIsPathResponse(true)

        const currentData = canvas.getGraphData();

        const nodesMap = new Map<number, GraphNode>(currentData.nodes.map(n => [n.id, n]))
        const linksMap = new Map<number, GraphLink>(currentData.links.map(l => [l.id, l]))

        formattedPaths.flatMap(p => p.nodes).forEach(n => {
            const node = nodesMap.get(n.id);
            if (node) {
                node.data.isPath = true;
            }
        });
        formattedPaths.flatMap(p => p.links).forEach(l => {
            const link = linksMap.get(l.id);

            if (link) {
                link.data.isPath = true;
                link.color = PATH_COLOR;
            }
        });

        // Filter for only new elements
        const newDataElements = {
            nodes: elements.nodes.filter(n => !nodesMap.has(n.id))
                .map(({ category, color, data, id, isPath, isPathSelected, visible }) => ({
                    color,
                    id,
                    labels: [category],
                    data: {
                        ...data,
                        isPath,
                        isPathSelected
                    },
                    visible,
                })),
            links: elements.links.filter(l => !linksMap.has(l.id))
                .map(({ color, id, source, target, data, isPath, isPathSelected, visible, label }) => ({
                    color: isPath ? PATH_COLOR : color,
                    id,
                    source,
                    target,
                    data: {
                        ...data,
                        isPath,
                        isPathSelected
                    },
                    visible,
                    relationship: label,
                }))
        }

        // Convert only new data to GraphData format
        const newGraphData = dataToGraphData(
            newDataElements,
            undefined,
            new Map(currentData.nodes.map(n => [n.id, n]))
        )

        // Merge with existing data
        canvasRef.current?.setGraphData({
            nodes: [...currentData.nodes, ...newGraphData.nodes],
            links: [...currentData.links, ...newGraphData.links]
        })

        if (elements.nodes.length !== 0 || elements.links.length !== 0) {
            setCooldownTicks(-1)
        }

        setTimeout(() => {
            const nodesMap = new Map<number, Node>(formattedPaths.flatMap(p => p.nodes.map((n: Node) => [n.id, n])))
            canvas.zoomToFit(2, (n: GraphNode) => formattedPaths.some(p => nodesMap.has(n.id)));
        }, 0)
    }

    const getTip = (className?: string) =>
        <>
            <button
                disabled={isSendMessage}
                className={cn("Tip", className)}
                onClick={() => {
                    const canvas = canvasRef.current

                    if (!canvas) return

                    setSugOpen(false)
                    setMessages(prev => {
                        const { messages, insertIndex } = RemoveLastPath(prev)
                        const queryMsg: Message = { type: MessageTypes.Query, text: "Create a path" }
                        return [...messages.slice(0, insertIndex), queryMsg, ...messages.slice(insertIndex)]
                    })

                    if (isPathResponse) {
                        setIsPathResponse(false)
                        graph.getElements().forEach(e => {
                            e.isPath = false
                            e.isPathSelected = false
                        })

                        const currentData = canvas.getGraphData();

                        [...currentData.nodes, ...currentData.links].forEach(element => {
                            element.data.isPath = false
                            element.data.isPathSelected = false

                            if ("source" in element) {
                                element.color = "#999999"
                            }
                        })

                        canvas.setGraphData(currentData)
                    }

                    setMessages(prev => [...prev, {
                        type: MessageTypes.Response,
                        text: "Please select a starting point and the end point. Select or press relevant item on the graph"
                    }, { type: MessageTypes.Path }])
                    setPath({})
                }}
            >
                <p className="text-center w-full">Show the path</p>
            </button>
            {
                SUGGESTIONS.map((s, i) => (
                    <button
                        disabled={isSendMessage}
                        type="submit"
                        key={i}
                        className={cn("Tip", className)}
                        onClick={() => {
                            sendQuery(undefined, s)
                            setSugOpen(false)
                        }}
                    >
                        <p className="text-center w-full">{s}</p>
                    </button>
                ))
            }
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
                    <img src="/dots.gif" width={100} height={10} alt="Waiting for response" />
                </div>
            )
        }
    }

    return (
        <div className="relative h-1 grow md:h-full flex flex-col justify-between px-6 pt-10 pb-4 gap-4">
            <main data-name="main-chat" ref={containerRef} className="grow flex flex-col overflow-y-auto gap-6 px-4">
                {
                    messages.length === 0 &&
                    <>
                        <h1 className="text-center text-2xl">What would you like to analyze?</h1>
                        <div className="flex flex-row flex-wrap gap-2 justify-center">
                            {getTip()}
                        </div>
                    </>
                }
                {
                    messages.map((message, index) => {
                        return getMessage(message, index)
                    })
                }
            </main>
            <footer className="flex gap-4 px-4 overflow-hidden min-h-fit">
                <DropdownMenu open={sugOpen} onOpenChange={setSugOpen}>
                    <DropdownMenuTrigger asChild>
                        <button data-name="lightbulb" className="p-4 border rounded-md hover:border-[#FF66B3] hover:bg-[#FFF0F7]">
                            <Lightbulb />
                        </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="flex flex-col gap-2 mb-4 w-[81.51dvw] md:w-[20dvw] overflow-y-auto" side="top">
                        {getTip("!w-full")}
                    </DropdownMenuContent>
                </DropdownMenu>
                <form className="grow flex items-center border rounded-md px-2" onSubmit={sendQuery}>
                    <input className="w-1 grow p-4 rounded-md focus-visible:outline-none" placeholder="Ask your question" onChange={handleQueryInputChange} value={query} />
                    <button disabled={isSendMessage} className={`bg-gray-200 p-2 rounded-md ${!isSendMessage && 'hover:bg-gray-300'}`}>
                        <ArrowRight color="white" />
                    </button>
                </form>
            </footer>
        </div>
    );
}
