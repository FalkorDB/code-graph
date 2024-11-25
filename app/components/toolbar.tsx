import { CircleDot, Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils"
import { Dispatch, MutableRefObject, RefObject, SetStateAction } from "react";
import { Node } from "./model";

interface Props {
    chartRef: MutableRefObject<any>
    setSelectedObj: Dispatch<SetStateAction<Node | undefined>>
    className?: string
}

export function Toolbar({ chartRef, setSelectedObj, className }: Props) {

    function handleZoomClick(changefactor: number) {
        let chart = chartRef.current
        if (chart) {
            chart.zoom(chart.zoom() * changefactor)
        }
        setSelectedObj(undefined)
    }

    return (
        <div className={cn("bg-white flex flex-row rounded overflow-hidden", className)}>
            <button
                className="border p-2"
                onClick={() => handleZoomClick(0.9)}
                title="Zoom Out"
            >
                <Minus />
            </button>
            <button
                className="border p-2"
                onClick={() => chartRef.current?.zoomToFit(500, 200)}
                title="Center"
            >
                <CircleDot />
            </button>
            <button
                className="border p-2"
                onClick={() => handleZoomClick(1.1)}
                title="Zoom In"
            >
                <Plus />
            </button>
        </div>
    )
}