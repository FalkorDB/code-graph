import { toast } from "@/components/ui/use-toast";
import { Dispatch, MutableRefObject, SetStateAction, use, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { AlignLeft, ArrowRight, ChevronDown, Lightbulb, Redo2, SendHorizonal, Undo2 } from "lucide-react";
import { Path } from "../page";
import Input from "./Input";
import { Graph } from "./model";
import { cn } from "@/lib/utils";
import { ElementDefinition } from "cytoscape";
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
}

interface Props {
    repo: string
    path: Path | undefined
    setPath: Dispatch<SetStateAction<Path | undefined>>
    graph: Graph
    chartRef: MutableRefObject<cytoscape.Core | null>
    selectedPathId: string | undefined
    setIsPathResponse: (isPathResponse: boolean) => void
}

export function Chat({ repo, path, setPath, graph, chartRef, selectedPathId, setIsPathResponse }: Props) {

    // Holds the messages in the chat
    const [messages, setMessages] = useState<Message[]>([]);

    // Holds the messages in the chat
    const [paths, setPaths] = useState<{ nodes: any[], edges: any[] }[]>([]);

    const [selectedPath, setSelectedPath] = useState<{ nodes: any[], edges: any[] }>();

    // Holds the user input while typing
    const [query, setQuery] = useState('');

    // A reference to the chat container to allow scrolling to the bottom
    const containerRef: React.RefObject<HTMLDivElement> = useRef(null);

    useEffect(() => {
        const path = paths.find((p) => [...p.edges, ...p.nodes].some((e: any) => e.id === selectedPathId))

        if (!path) return

        handelSetSelectedPath(path)
    }, [selectedPathId])

    useEffect(() => {
        handelSubmit()
    }, [path])

    const handelSetSelectedPath = (p: { nodes: any[], edges: any[] }) => {
        const chart = chartRef.current

        if (!chart) return

        setSelectedPath(prev => {
            prev?.edges.forEach(element => {
                const e = chart.elements().filter(el => el.id() == element.id)
                if (!p.edges.some(e => e.id === element.id)) {
                    e.style({
                        width: 0.5,
                        "line-style": "dashed",
                        "line-color": "pink",
                        "arrow-scale": 0.3,
                        "target-arrow-color": "pink",
                    })
                }
            })

            return p
        });

        p.edges.forEach(element => {
            const e = chart.elements().filter(el => el.id() == element.id)
            e.style({
                width: 1,
                "line-style": "solid",
                "line-color": "pink",
                "arrow-scale": 0.6,
                "target-arrow-color": "pink",
            })
        })

        const elementsInPath = chart.elements().filter((element) => {
            return [...p.nodes, ...p.edges].some((node) => node.id == element.id())
        });
        elementsInPath.layout(LAYOUT).run();
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
            setQuery("")
            return
        }

        setMessages((messages) => [...messages, { text: q, type: MessageTypes.Query }, { text: "", type: MessageTypes.Pending }]);

        return fetch(`/api/repo/${repo}?q=${encodeURIComponent(q)}&type=text`, {
            method: 'GET'
        }).then(async (result) => {
            if (result.status >= 300) {
                throw Error(await result.text())

            }

            return result.json()
        }).then(data => {
            // Create an array of messages from the current messages remove the last pending message and add the new response
            setMessages(function (messages) {
                if (messages[messages.length - 1].type === MessageTypes.Pending) {
                    // Remove the last pending message if exists
                    messages = messages.slice(0, -1);
                }
                return [...messages, { text: data.result, type: MessageTypes.Response }];
            });
            setQuery("")
        }).catch((error) => {
            setMessages(function (messages) {
                if (messages[messages.length - 1].type === MessageTypes.Pending) {
                    // Remove the last pending message if exists
                    return messages.slice(0, -1);
                }
                return messages
            });
            setQuery("")
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: error.message,
            });
        });
    }

    // A function that handles the click event
    async function handleQueryClick(event: any) {
        event.preventDefault();
        return sendQuery(query.trim());
    }

    // Scroll to the bottom of the chat on new message
    useEffect(() => {
        containerRef.current?.scrollTo(0, containerRef.current?.scrollHeight);
    }, [messages]);

    const handelSubmit = async () => {
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

        const formattedPaths: { nodes: any[], edges: any[] }[] = json.result.paths.map((p: any) => ({ nodes: p.filter((node: any, i: number) => i % 2 === 0), edges: p.filter((edge: any, i: number) => i % 2 !== 0) }))
        const addedElements: ElementDefinition[] = []
        formattedPaths.forEach((p: any) => addedElements.push(...graph.extend(p, false, path)))
        formattedPaths.forEach(p => p.edges.forEach(e => e.id = `_${e.id}`))
        console.log(formattedPaths);
        graph.Elements.forEach((element: any) => {
            const { id } = element.data
            if (!formattedPaths.some((p: any) => [...p.nodes, ...p.edges].some((el: any) => el.id == id))) {
                const e = chart.elements().filter(el => el.id() == id)

                if (e.isNode()) {
                    e.style({
                        "color": "gray",
                        "background-color": "gray",
                        "opacity": 0.5
                    });
                }

                if (e.isEdge()) {
                    e.style({
                        "line-color": "gray",
                        "target-arrow-color": "gray",
                        "opacity": 0.5
                    });
                }
            }
        })
        chart.add(addedElements)
        console.log(formattedPaths.flatMap(p => [...p.nodes, ...p.edges].map(e => e.id)));
        const elements = chart.elements().filter((element) => {
            console.log(element.id());
            return formattedPaths.some(p => [...p.nodes, ...p.edges].some((node) => node.id == element.id()))
        });
        elements.layout(LAYOUT).run()
        setPaths(formattedPaths)
        setMessages(prev => [...prev.slice(0, -2), { type: MessageTypes.PathResponse }])
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
                    <p className="text-sm">{message.text}</p>
                </div>
            )
            case MessageTypes.Response: return (
                <div key={index} className="flex flex-col gap-2">
                    <div className="flex gap-2">
                        <Undo2 className="rotate-180" />
                        <h1 className="text-lg font-medium">Answer</h1>
                    </div>
                    <p className="text-sm">{message.text}</p>
                </div>
            )
            case MessageTypes.Text: return (
                <p key={index} >{message.text}</p>
            )
            case MessageTypes.Path: {
                return (
                    <div className="flex flex-col gap-4" key={index}>
                        <Input
                            graph={graph}
                            onValueChange={({ name, id }) => setPath(prev => ({ start: { name, id }, end: prev?.end }))}
                            value={path?.start?.name}
                            placeholder="Start typing starting point"
                            type="text"
                            icon={<ChevronDown color="gray" />}
                            node={path?.start}
                        />
                        <Input
                            graph={graph}
                            value={path?.end?.name}
                            onValueChange={({ name, id }) => setPath(prev => ({ end: { name, id }, start: prev?.start }))}
                            placeholder="Start typing end point"
                            type="text"
                            icon={<ChevronDown color="gray" />}
                            node={path?.end}
                        />
                    </div>
                )
            }
            case MessageTypes.PathResponse: return (
                <div key={index} className="flex flex-col gap-2">
                    {
                        paths.map((p, i: number) => (
                            <button
                                key={i}
                                className={cn("flex text-wrap border p-2 gap-2", p.nodes.length === selectedPath?.nodes.length && selectedPath?.nodes.every(node => p?.nodes.some((n) => n.id === node.id)) && "border-[#FF66B3] bg-[#FFF0F7]")}
                                onClick={() => handelSetSelectedPath(p)}
                            >
                                <p className="font-bold">#{i}</p>
                                <p>
                                    {
                                        p.nodes.map((node: any, j: number) => (
                                            <span key={j} className={cn((j === 0 || j === p.nodes.length - 1) && "font-bold")}>
                                                {` - ${node.properties.name}`}
                                            </span>
                                        ))
                                    }
                                </p>
                            </button>
                        ))
                    }
                </div>
            )
            case MessageTypes.Tip: return (
                <div key={index} className="flex flex-col gap-6">
                    <button
                        className="flex gap-2 p-4 border bg-gray-100 hover:bg-gray-200 rounded-md"
                    >
                        <Lightbulb />
                        <div className="flex flex-col gap-2 text-start">
                            <h1 className="font-bold">Show unreadable code</h1>
                            <p>Remove it if unnecessary or fix logic issues.</p>
                        </div>
                    </button>
                    <button
                        className="flex gap-2 p-4 border bg-gray-100 hover:bg-gray-200 rounded-md"
                        onClick={() => {
                            setMessages(prev => [
                                ...prev,
                                { type: MessageTypes.Query, text: "Create a path" },
                                {
                                    type: MessageTypes.Response,
                                    text: "Please select a starting point and the end point. Select or press relevant item on the graph"
                                },
                                { type: MessageTypes.Path }
                            ])
                            setPath({})
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
        <div className="h-full flex flex-col gap-5">
            <main ref={containerRef} className="h-1 grow flex flex-col gap-6 overflow-auto p-12 pb-0">
                {
                    messages.length === 0 &&
                    <div className="flex flex-col gap-16">
                        <div className="flex flex-col gap-4">
                            <h1 className="text-xl font-extrabold">WELCOME TO OUR ASSISTANCE SERVICE</h1>
                            <span className="text-gray-500 text-lg">
                                We can help you access and update only the needed
                                data via paths, optimizing network requests with
                                batching and catching for better performance.
                            </span>
                        </div>
                        {getMessage({ type: MessageTypes.Tip })}
                    </div>
                }
                {
                    messages.map((message, index) => {
                        return getMessage(message, index)
                    })
                }
            </main>
            <footer>
                {repo &&
                    <div className="flex gap-4 p-6">
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
