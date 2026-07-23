import { Dispatch, SetStateAction, type ReactNode } from "react";
import { Link, Node } from "./model";
import { Copy, SquareArrowOutUpRight, X } from "lucide-react";
import SyntaxHighlighter from 'react-syntax-highlighter';
import { dark } from 'react-syntax-highlighter/dist/esm/styles/hljs';

interface Props {
    obj: Node | Link | undefined;
    setObj: Dispatch<SetStateAction<Node | Link | undefined>>;
    url: string;
}

const excludedProperties = [
    "category",
    "label",
    "color",
    "expand",
    "collapsed",
    "isPath",
    "visible",
    "index",
    "curve",
    "__indexColor",
    "isPathSelected",
    "__controlPoints",
    "x",
    "y",
    "vx",
    "vy",
    "fx",
    "fy",
]

function isPlainObject(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value)
}

function renderSourceBlock(value: string) {
    return (
        <SyntaxHighlighter
            language="python"
            style={{
                ...dark,
                hljs: {
                    ...dark.hljs,
                    maxHeight: `9rem`,
                    background: 'transparent',
                    padding: 2,
                }
            }}
        >
            {value}
        </SyntaxHighlighter>
    )
}

function renderJsonValue(value: unknown, path: string[]): ReactNode {
    const key = path[path.length - 1]

    if (key === "src" && typeof value === "string") {
        return renderSourceBlock(value)
    }

    if (Array.isArray(value)) {
        return (
            <details className="ml-2 border-l border-border pl-3">
                <summary className="cursor-pointer text-card-foreground">Array({value.length})</summary>
                <div className="mt-2 flex flex-col gap-2">
                    {value.map((item, index) => (
                        <div key={index} className="flex gap-2">
                            <span className="text-primary">[{index}]</span>
                            <div className="min-w-0 flex-1 break-words text-card-foreground">
                                {renderJsonValue(item, [...path, String(index)])}
                            </div>
                        </div>
                    ))}
                </div>
            </details>
        )
    }

    if (isPlainObject(value)) {
        const entries = Object.entries(value).filter(([nestedKey]) => !excludedProperties.includes(nestedKey))

        return (
            <details className="ml-2 border-l border-border pl-3">
                <summary className="cursor-pointer text-card-foreground">Object({entries.length})</summary>
                <div className="mt-2 flex flex-col gap-2">
                    {entries.map(([nestedKey, nestedValue]) => (
                        <div key={nestedKey} className="flex gap-2">
                            <span className="text-primary">{nestedKey}:</span>
                            <div className="min-w-0 flex-1 break-words text-card-foreground">
                                {renderJsonValue(nestedValue, [...path, nestedKey])}
                            </div>
                        </div>
                    ))}
                </div>
            </details>
        )
    }

    return <span className="text-card-foreground">{String(value)}</span>
}

export default function DataPanel({ obj, setObj, url }: Props) {
    if (!obj) return null;

    const type = "category" in obj
    const label = type ? `${obj.category}: ${obj.data.name}` : obj.label
    const object = Object.entries(obj).filter(([k]) => !excludedProperties.includes(k))

    return (
        <>
            <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-20" />
            <div data-name="node-details-panel" className="z-30 absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 md:-top-10 md:left-20 md:transform-none bg-card text-card-foreground shadow-lg rounded-lg flex flex-col max-h-[90vh] w-[90vw] md:max-h-[88vh] md:w-[56vw] overflow-hidden">
                <header className="bg-muted flex items-center gap-8 justify-between p-8">
                    <p title={label} className="truncate font-bold">{label.toUpperCase()}</p>
                    <button onClick={() => setObj(undefined)}>
                        <X />
                    </button>
                </header>
                <main className="bg-card flex flex-col grow overflow-y-auto p-4">
                    {object.map(([key, value]) => (
                        <div key={key} className="flex gap-2">
                            <p className="text-primary">{key}:</p>
                            <div className="min-w-0 flex-1 break-words">
                                {renderJsonValue(value, [key])}
                            </div>
                        </div>
                    ))}
                </main>
                <footer className="bg-muted flex items-center justify-between p-4">
                    {"category" in obj && (
                        <>
                            <button
                                className="flex items-center gap-2 p-2"
                                title="Copy src to clipboard"
                                onClick={() => navigator.clipboard.writeText(obj.data.src || "")}
                            >
                                <Copy />
                                Copy
                            </button>
                            <a
                                className="flex items-center gap-2 p-2"
                                href={url}
                                rel="noopener noreferrer"
                                target="_blank"
                                title="Go to repo"
                            >
                                <SquareArrowOutUpRight />
                                Go to repo
                            </a>
                        </>
                    )}
                </footer>
            </div>
        </>
    )
}