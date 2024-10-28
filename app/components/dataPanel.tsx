import { Dispatch, SetStateAction, useEffect, useRef, useState } from "react";
import { Node } from "./model";
import { ChevronLeft, ChevronRight, Copy, SquareArrowOutUpRight, X } from "lucide-react";

interface Props {
    obj: Node | undefined;
    setObj: Dispatch<SetStateAction<Node | undefined>>;
    url: string;
}

const excludedProperties = [
    "category",
    "color",
    "expand",
    "collapsed",
    "isPath",
]

export default function DataPanel({ obj, setObj, url }: Props) {

    if (!obj) return null;

    const label = `${obj.category}: ${obj.name}`
    const object = Object.fromEntries(Object.entries(obj).filter(([k]) => !excludedProperties.includes(k)))

    return (
        <div className="z-20 absolute -top-10 left-20 bg-gray-600 text-white shadow-lg rounded-lg flex flex-col min-h-[50%] max-h-[70%] min-w-[40%] max-w-[70%] overflow-hidden" >
            <header className="bg-black flex items-center gap-8 justify-between p-8">
                <div className="border-b border-black text-bottom">
                    <p title={label} className="truncate font-bold">{label.toUpperCase()}</p>
                </div>
                <button onClick={() => setObj(undefined)}>
                    <X color="white" />
                </button>
            </header>
            <main className="flex flex-col grow overflow-auto overflow-x-hidden p-4">
                <pre className="text-wrap">
                    {JSON.stringify(object, null, 1)
                        .replace(/({|}|\[|\]|,)/g, match => match === '}' || match === "]" ? `\n${match}` : `${match}\n`).slice(1, -1)
                    }
                </pre>
            </main>
            <footer className="bg-black flex items-center justify-between p-4">
                <button
                    className="flex items-center gap-2 p-2"
                    title="Copy to clipboard"
                    onClick={() => navigator.clipboard.writeText(JSON.stringify(obj))}
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
            </footer>
        </div>
    )
}