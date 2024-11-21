import { CircleDot, Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils"
import { Dispatch, RefObject, SetStateAction } from "react";
import { Node } from "./model";

interface Props {
    chartRef: RefObject<cytoscape.Core>
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

    function handleCenterClick() {
        let chart = chartRef.current
        if (chart) {
            chart.fit(undefined, 80)
            chart.center()
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
                onClick={() => handleCenterClick()}
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