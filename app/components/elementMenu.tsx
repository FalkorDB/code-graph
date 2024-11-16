"use client"

import { useEffect, useState } from "react";
import { Node } from "./model";
import { ChevronLeft, ChevronRight, ChevronsLeftRight, ChevronsRightLeft, Copy, Globe, Maximize2 } from "lucide-react";
import DataPanel from "./dataPanel";
import { Position } from "cytoscape";

interface Props {
    obj: Node | undefined;
    position: Position | undefined;
    url: string;
    handelMaximize: () => void;
    parentWidth: number;
}


export default function ElementMenu({ obj, position, url, handelMaximize, parentWidth }: Props) {
    const [currentObj, setCurrentObj] = useState<Node>();
    const [containerWidth, setContainerWidth] = useState(0);

    useEffect(() => {
        setCurrentObj(undefined)
    }, [obj])

    if (!obj || !position) return null

    const objURL = obj.category === "File"
        ? `${url}/tree/master/${obj.path}/${obj.name}`
        : `${url}/tree/master/${obj.path}#L${obj.src_start}-L${obj.src_end + 1}`

    return (
        <>
            <div
                ref={(ref) => {
                    if (!ref) return
                    setContainerWidth(ref.clientWidth)
                }}
                className="absolute z-10 bg-black rounded-lg shadow-lg flex divide-x divide-[#434343]"
                style={{
                    left: position.x - containerWidth / 2,
                    top: position.y + 5
                }}
            >
                <button
                    className="p-2"
                    title="Copy src to clipboard"
                    onClick={() => navigator.clipboard.writeText(obj.src)}
                >
                    <Copy color="white" />
                </button>
                <a
                    className="p-2"
                    href={objURL}
                    target="_blank"
                    title="Go to repo"
                    onClick={() => {
                        const newTab = window.open(objURL, '_blank');

                        if (!obj.src_start || !obj.src_end || !newTab) return

                        newTab.scroll({
                            top: obj.src_start,
                            left: obj.src_end,
                            behavior: 'smooth'
                        })
                    }}
                >
                    <Globe color="white" />
                </a>
                <button
                    className="flex p-2"
                    title="View Node"
                    onClick={() => setCurrentObj(obj)}
                >
                    <ChevronsLeftRight color="white" />
                </button>
                <button
                    className="p-2"
                    onClick={() => handelMaximize()}
                >
                    <Maximize2 color="white" />
                </button>
            </div>
            <DataPanel
                obj={currentObj}
                setObj={setCurrentObj}
                url={objURL}
            />
        </>
    )
}