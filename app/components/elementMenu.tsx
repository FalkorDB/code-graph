"use client"

import { Dispatch, SetStateAction, useEffect, useState } from "react";
import { Node } from "./model";
import { ChevronLeft, ChevronRight, ChevronsLeftRight, Copy, EyeOff, Globe, Maximize2, Minimize2, Waypoints } from "lucide-react";
import DataPanel from "./dataPanel";
import { EventObject, Position } from "cytoscape";
import { Path } from "../page";

interface Props {
    obj: Node | undefined;
    objects: Node[];
    setPath: Dispatch<SetStateAction<Path | undefined>>;
    handelRemove: (nodes: number[]) => void;
    position: Position | undefined;
    url: string;
    handelMaximize: () => void;
    parentWidth: number;
}

export default function ElementMenu({ obj, objects, setPath, handelRemove, position, url, handelExpand, parentWidth }: Props) {
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
                    left: Math.max(-34, Math.min(position.x - containerWidth / 2, parentWidth + 34 - containerWidth)),
                    top: position.y + 5,
                }}
            >
                {
                    objects.some(o => o.id === obj.id) && objects.length > 1 ?
                        <>
                            {
                                objects.length === 2 &&
                                <button
                                    className="p-2"
                                    title="Create a path"
                                    onClick={() => setPath({ start: { id: Number(objects[0].id), name: objects[0].name }, end: { id: Number(objects[1].id), name: objects[1].name } })}
                                >
                                    <Waypoints color="white" />
                                </button>
                            }
                            <button
                                className="p-2"
                                title="Remove"
                                onClick={() => handelRemove(objects.map(o => Number(o.id)))}
                            >
                                <EyeOff color="white" />
                            </button>
                            <button
                                className="p-2"
                                onClick={() => handelExpand(objects, true)}
                            >
                                <Maximize2 color="white" />
                            </button>
                            <button
                                className="p-2"
                                onClick={() => handelExpand(objects, false)}
                            >
                                <Minimize2 color="white" />
                            </button>
                        </>
                        : <>
                            <button
                                className="p-2"
                                title="Copy src to clipboard"
                                onClick={() => navigator.clipboard.writeText(obj.src || "")}
                            >
                                <Copy color="white" />
                            </button>
                            <button
                                className="p-2"
                                title="Remove"
                                onClick={() => handelRemove([Number(obj.id)])}
                            >
                                <EyeOff color="white" />
                            </button>
                            <a
                                className="p-2"
                                href={objURL}
                                target="_blank"
                                title="Go to repo"
                                onClick={() => {
                                    window.open(objURL, '_blank');
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
                                onClick={() => handelExpand(objects, true)}
                            >
                                <Maximize2 color="white" />
                            </button>
                            <button
                                className="p-2"
                                onClick={() => handelExpand(objects, false)}
                            >
                                <Minimize2 color="white" />
                            </button>
                        </>
                }
            </div>
            <DataPanel
                obj={currentObj}
                setObj={setCurrentObj}
                url={objURL}
            />
        </>
    )
}