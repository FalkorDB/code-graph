import { toast } from "@/components/ui/use-toast";
import { Dispatch, FormEvent, SetStateAction, useEffect, useRef, useState } from "react";
import { AlignLeft, ArrowRight, ChevronDown, Lightbulb, Loader2, Undo2 } from "lucide-react";
import { Message, MessageTypes, Path, PathData, PATH_COLOR, createMessage } from "@/lib/utils";
import Input from "./Input";
import { Graph, GraphData, Node } from "./model";
import { cn, GraphRef } from "@/lib/utils";
import { TypeAnimation } from "react-type-animation";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";

const AUTH_HEADERS: HeadersInit = import.meta.env.VITE_SECRET_TOKEN
    ? { 'Authorization': `Bearer ${import.meta.env.VITE_SECRET_TOKEN}` }
    : {};
import { GraphNode } from "@falkordb/canvas";
import { convertToCanvasData } from "./ForceGraph";

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

const RemoveLastPath = (messages: Message[], includeQuery = false): RemoveLastPathResult => {
    // Find the last Path marker (the pending "select start/end" state)
    const index = messages.findLastIndex((m) => m.type === MessageTypes.Path)

    if (index === -1) {
        return { messages, insertIndex: messages.length }
    }

    // The Path marker is always preceded by Response("Please select...").
    // Optionally also remove the Query("Create a path") before it.
    let groupStart = index;
    if (index > 0 && messages[index - 1].type === MessageTypes.Response) {
        groupStart = index - 1;
        if (includeQuery && groupStart > 0 && messages[groupStart - 1].type === MessageTypes.Query) {
            groupStart = groupStart - 1;
        }
    }

    const cleaned = [...messages.slice(0, groupStart), ...messages.slice(index + 1)]

    return { messages: cleaned, insertIndex: cleaned.length }
}

export function Chat({ messages, setMessages, query, setQuery, selectedPath, setSelectedPath, setChatOpen, repo, path, setPath, graph, selectedPathId, isPathResponse, setIsPathResponse, canvasRef, paths, setPaths }: Props) {

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

        setIsPathResponse(true)
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

        canvas.setGraphData(convertToCanvasData(graph.Elements))

        setTimeout(() => {
            canvas.zoomToFit(2, (n: GraphNode) => pNodeIds.has(n.id));
        }, 300)
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

        setMessages((messages) => [...messages, createMessage({ text: q, type: MessageTypes.Query }), createMessage({ type: MessageTypes.Pending })]);

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
                return [...prev, createMessage({ type: MessageTypes.Response, text: "Sorry but I couldn't answer your question, please try rephrasing." })];
            });
            return
        }

        const json = await result.json()

        setMessages((prev) => {
            prev = prev.slice(0, -1);
            return [...prev, createMessage({ text: json.response, type: MessageTypes.Response })];
        });

    }

    const handleSubmit = async () => {
        const canvas = canvasRef.current

        if (!canvas) return

        setSelectedPath(undefined)

        if (!path?.start?.id || !path.end?.id) return

        const pathMessage = [createMessage({
            type: MessageTypes.Response,
            text: "Please select a starting point and the end point. Select or press relevant item on the graph"
        }), createMessage({ type: MessageTypes.Path })]

        setPath(undefined)
        let insertIndex = 0
        setMessages((prev) => {
            const { messages, insertIndex: idx } = RemoveLastPath(prev)
            insertIndex = idx
            const pending: Message = createMessage({ type: MessageTypes.Pending })
            return [...messages.slice(0, insertIndex), pending, ...messages.slice(insertIndex)]
        })

        const result = await fetch(`/api/find_paths`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...AUTH_HEADERS,
            },
            body: JSON.stringify({ repo: repo, src: Number(path.start.id), dest: Number(path.end.id) }),
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

        if (json.paths.length === 0) {
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

        const formattedPaths: PathData[] = json.paths.map((p: any) => ({ nodes: p.filter((_n: any, i: number) => i % 2 === 0), links: p.filter((l: any, i: number) => i % 2 !== 0) }))
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
            createMessage({ type: MessageTypes.PathResponse, paths: formattedPaths, graphName: graph.Id }),
            ...prev.slice(insertIndex + 1),
        ]);
        setIsPathResponse(true)

        // Mark path elements on the model
        formattedPaths.flatMap(p => p.nodes).forEach(n => {
            const node = graph.Elements.nodes.find(gn => gn.id === n.id);
            if (node) {
                node.isPath = true;
            }
        });
        formattedPaths.flatMap(p => p.links).forEach(l => {
            const link = graph.Elements.links.find(gl => gl.id === l.id);
            if (link) {
                link.isPath = true;
                link.color = PATH_COLOR;
            }
        });

        // Update the canvas from the model
        canvasRef.current?.setGraphData(convertToCanvasData(graph.Elements))
        
        // Zoom to fit all path nodes after coloring
        const pathNodeIds = new Set(formattedPaths.flatMap(p => p.nodes).map(n => n.id))
        if (pathNodeIds.size > 0 && canvasRef.current) {
            canvasRef.current.zoomToFit(1, (n: any) => pathNodeIds.has(n.id))
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
                        const { messages } = RemoveLastPath(prev, true)
                        const queryMsg: Message = createMessage({ type: MessageTypes.Query, text: "Create a path" })
                        return [...messages, queryMsg]
                    })

                    if (isPathResponse) {
                        setIsPathResponse(false)
                        graph.getElements().forEach(e => {
                            e.isPath = false
                            e.isPathSelected = false
                        })

                        // Reset link colors on the model
                        graph.Elements.links.forEach(link => {
                            link.color = "#999999"
                        })

                        canvas.setGraphData(convertToCanvasData(graph.Elements))
                    }

                    setMessages(prev => [...prev, createMessage({
                        type: MessageTypes.Response,
                        text: "Please select a starting point and the end point. Select or press relevant item on the graph"
                    }), createMessage({ type: MessageTypes.Path })])
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
                <div key={message.id} className="flex flex-col gap-2">
                    <div className="flex gap-2">
                        <AlignLeft />
                        <h1 className="text-lg font-medium">You</h1>
                    </div>
                    <p className="break-words whitespace-pre-wrap">{message.text}</p>
                </div>
            )
            case MessageTypes.Response: return (
                <div key={message.id} className="flex flex-col gap-2">
                    <div className="flex gap-2">
                        <Undo2 className="rotate-180" />
                        <h1 className="text-lg font-medium break-words whitespace-pre-wrap">Answer</h1>
                    </div>
                    <TypeAnimation
                        sequence={[message.text!]}
                        speed={60}
                        wrapper="span"
                        cursor={false}
                    />
                </div>
            )
            case MessageTypes.Text: return (
                <p key={message.id} >{message.text}</p>
            )
            case MessageTypes.Path: {
                return (
                    <div className="flex flex-col gap-4" key={message.id}>
                        <Input
                            parentClassName="w-full"
                            graph={graph}
                            onValueChange={({ name, id }) => setPath(prev => ({ start: { name, id }, end: prev?.end }))}
                            value={path?.start?.name || ""}
                            placeholder="Start typing starting point"
                            type="text"
                            icon={<ChevronDown className="text-muted-foreground" />}
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
                            icon={<ChevronDown className="text-muted-foreground" />}
                            node={path?.end}
                            scrollToBottom={() => containerRef.current?.scrollTo(0, containerRef.current?.scrollHeight)}
                        />
                    </div>
                )
            }
            case MessageTypes.PathResponse: return (
                <div key={message.id} className="flex flex-col gap-2">
                    <div className="flex gap-2">
                        <Undo2 className="rotate-180" />
                        <h1 className="text-lg font-medium break-words whitespace-pre-wrap">Answer</h1>
                    </div>
                    {
                        message.paths &&
                        message.paths.map((p, i: number) => (
                            <button
                                key={i}
                                className={cn(
                                    "flex text-wrap border p-2 gap-2 rounded-md",
                                    p.nodes.length === selectedPath?.nodes.length &&
                                    selectedPath?.nodes.every((node, i) => p?.nodes[i]?.id === node.id) &&
                                    "border-[#ffde21] bg-[#ffde2133]",
                                    message.graphName !== graph.Id && "opacity-50 bg-secondary"
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

                                    if (selectedPath?.nodes.every((node, i) => p?.nodes[i]?.id === node.id) && selectedPath.nodes.length === p.nodes.length) return

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
                <div key={message.id} className="flex gap-2">
                    <div className="inline-flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Thinking...</span>
                    </div>
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
                        <button data-name="lightbulb" className="p-4 border rounded-md hover:border-primary hover:bg-primary/5 transition-colors">
                            <Lightbulb />
                        </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="flex flex-col gap-2 mb-4 w-[81.51dvw] md:w-[20dvw] overflow-y-auto" side="top">
                        {getTip("!w-full")}
                    </DropdownMenuContent>
                </DropdownMenu>
                <form className="grow flex items-center border rounded-md px-2 focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/50 transition-colors" onSubmit={sendQuery}>
                    <input className="w-1 grow p-4 rounded-md bg-transparent focus-visible:outline-none" placeholder="Ask your question" onChange={handleQueryInputChange} value={query} />
                    <Button disabled={isSendMessage} variant="default" size="icon" className="shrink-0">
                        <ArrowRight />
                    </Button>
                </form>
            </footer>
        </div>
    );
}
