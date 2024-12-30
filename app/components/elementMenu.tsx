"use client"

import { Dispatch, RefObject, SetStateAction, useEffect, useState } from "react";
import { Node } from "./model";
import { ChevronsLeftRight, Copy, EyeOff, Globe, Maximize2, Minimize2, Waypoints } from "lucide-react";
import DataPanel from "./dataPanel";
import { Path } from "../page";
import { Position } from "./graphView";

interface Props {
    obj: Node | undefined;
    objects: Node[];
    setPath: Dispatch<SetStateAction<Path | undefined>>;
    handleRemove: (nodes: number[]) => void;
    position: Position | undefined;
    url: string;
    handelExpand: (nodes: Node[], expand: boolean) => void;
    parentRef: RefObject<HTMLDivElement>;
}


export default function ElementMenu({ obj, objects, setPath, handleRemove, position, url, handelExpand, parentRef }: Props) {
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
                    left: Math.max(-34, Math.min(position.x - 33 - containerWidth / 2, (parentRef?.current?.clientWidth || 0) + 32 - containerWidth)),
                    top: Math.min(position.y - 153, (parentRef?.current?.clientHeight || 0) - 9),
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
                                onClick={() => handleRemove(objects.map(o => o.id))}
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
                                onClick={() => handleRemove([obj.id])}
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
                                onClick={() => handelExpand([obj], true)}
                            >
                                <Maximize2 color="white" />
                            </button>
                            <button
                                className="p-2"
                                onClick={() => handelExpand([obj], false)}
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