import { Dispatch, SetStateAction } from "react";
import { JSONTree } from 'react-json-tree';
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
    "isPathSelected",
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

export default function DataPanel({ obj, setObj, url }: Props) {
    if (!obj) return null;

    const type = "category" in obj
    const label = type ? `${obj.category}: ${obj.name}` : obj.label
    const object = Object.entries(obj).filter(([k]) => !excludedProperties.includes(k))

    return (
        <>
            <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-20" />
            <div data-name="node-details-panel" className="z-30 absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 md:-top-10 md:left-20 md:transform-none bg-[#343434] text-white shadow-lg rounded-lg flex flex-col max-h-[90vh] w-[90vw] md:max-h-[88vh] md:w-[56vw] overflow-hidden">
                <header className="bg-[#191919] flex items-center gap-8 justify-between p-8">
                    <p title={label} className="truncate font-bold">{label.toUpperCase()}</p>
                    <button onClick={() => setObj(undefined)}>
                        <X color="white" />
                    </button>
                </header>
                <main className="bg-[#343434] flex flex-col grow overflow-y-auto p-4">
                    {
                        object.map(([key, value]) => (
                            <div key={key} className="flex gap-2">
                                <p className="text-[#FF804D]">{key}:</p>
                                {
                                    key === "src" ?
                                        <SyntaxHighlighter
                                            language="python"
                                            style={{
                                                ...dark,
                                                hljs: {
                                                    ...dark.hljs,
                                                    maxHeight: `9rem`,
                                                    background: '#343434',
                                                    padding: 2,
                                                }
                                            }}
                                        >
                                            {value}
                                        </SyntaxHighlighter>
                                        : typeof value === "object" ?
                                            <JSONTree
                                                data={Object.fromEntries(Object.entries(value).filter(([k]) => !excludedProperties.includes(k)))}
                                                theme={{
                                                    base00: '#343434', // background
                                                    base01: '#000000',
                                                    base02: '#CE9178',
                                                    base03: '#CE9178', // open values
                                                    base04: '#CE9178',
                                                    base05: '#CE9178',
                                                    base06: '#CE9178',
                                                    base07: '#CE9178',
                                                    base08: '#CE9178',
                                                    base09: '#b5cea8', // numbers
                                                    base0A: '#CE9178',
                                                    base0B: '#CE9178', // close values
                                                    base0C: '#CE9178',
                                                    base0D: '#99E4E5', // * keys
                                                    base0E: '#ae81ff',
                                                    base0F: '#cc6633'
                                                }}
                                                valueRenderer={(valueAsString, value, keyPath) => {
                                                    if (keyPath === "src") {
                                                        return <SyntaxHighlighter
                                                            language="python"
                                                            style={{
                                                                    ...dark,
                                                                    hljs: {
                                                                        ...dark.hljs,
                                                                        maxHeight: `9rem`,
                                                                        background: '#343434',
                                                                        padding: 2,
                                                                    }
                                                                }}
                                                            >
                                                                {value as string}
                                                            </SyntaxHighlighter>
                                                    }
                                                    return <span className="text-white">{value as string}</span>
                                                }}
                                            />
                                            : <span className="text-white">{value}</span>
                                }
                            </div>
                        ))
                    }
                </main>
                <footer className="bg-[#191919] flex items-center justify-between p-4">
                    {
                        "category" in obj &&
                        <>
                            <button
                                className="flex items-center gap-2 p-2"
                                title="Copy src to clipboard"
                                onClick={() => navigator.clipboard.writeText(obj.src || "")}
                            >
                                <Copy color="white" />
                                Copy
                            </button>
                            <a
                                className="flex items-center gap-2 p-2"
                                href={url}
                                target="_blank"
                                title="Go to repo"
                                onClick={() => {
                                    const newTab = window.open(url, '_blank');

                                    if (!obj.src_start || !obj.src_end || !newTab) return

                                    newTab.scroll({
                                        top: obj.src_start,
                                        behavior: 'smooth'
                                    })
                                }}
                            >
                                <SquareArrowOutUpRight color="white" />
                                Go to repo
                            </a>
                        </>
                    }
                </footer>
            </div>
        </>
    )
}