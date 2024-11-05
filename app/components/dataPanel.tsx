import { Dispatch, SetStateAction } from "react";
import { Node } from "./model";
import { Copy, SquareArrowOutUpRight, X } from "lucide-react";

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
    "isPathStartEnd"
]

export default function DataPanel({ obj, setObj, url }: Props) {

    if (!obj) return null;

    const label = `${obj.category}: ${obj.name}`
    const object = Object.entries(obj).filter(([k]) => !excludedProperties.includes(k))

    return (
        <div className="z-20 absolute -top-10 left-20 bg-[#343434] text-white shadow-lg rounded-lg flex flex-col min-h-[65%] max-h-[88%] max-w-[56%] overflow-hidden" >
            <header className="bg-[#191919] flex items-center gap-8 justify-between p-8">
                <div className="border-b border-black text-bottom">
                    <p title={label} className="truncate font-bold">{label.toUpperCase()}</p>
                </div>
                <button onClick={() => setObj(undefined)}>
                    <X color="white" />
                </button>
            </header>
            <main className="flex flex-col grow overflow-auto overflow-x-hidden p-4 justify-center">
                {
                    object.map(([key, value]) => (
                        <div key={key} className="flex gap-2">
                            <p className="text-[#FF804D]">{key}:</p>
                            <p className="text-white">{value}</p>
                        </div>
                    ))
                }
            </main>
            <footer className="bg-[#191919] flex items-center justify-between p-4">
                <button
                    className="flex items-center gap-2 p-2"
                    title="Copy src to clipboard"
                    onClick={() => navigator.clipboard.writeText(obj.src)}
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