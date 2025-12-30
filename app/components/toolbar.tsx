import { Download, Fullscreen, ZoomIn, ZoomOut } from "lucide-react";
import { cn } from "@/lib/utils"
import { GraphRef } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";

interface Props {
    canvasRef: GraphRef
    className?: string
    handleDownloadImage?: () => void
    setCooldownTicks: (ticks?: 0) => void
    cooldownTicks: number | undefined
}

export function Toolbar({ canvasRef, className, handleDownloadImage, setCooldownTicks, cooldownTicks }: Props) {

    const handleZoomClick = (changefactor: number) => {
        const canvas = canvasRef.current

        if (canvas) {
            canvas.zoom(canvas.getZoom() * changefactor)
        }
    }

    const handleCenterClick = () => {
        const canvas = canvasRef.current

        if (canvas) {
            canvas.zoomToFit()
        }
    }

    return (
        <div className={cn("flex flex-row items-center rounded overflow-hidden p-1", className)}>
            <Switch
                className="ml-4 pointer-events-auto data-[state=unchecked]:bg-border"
                checked={cooldownTicks === undefined}
                onCheckedChange={() => {
                    setCooldownTicks(cooldownTicks === undefined ? 0 : undefined)
                }}
            />
            <button
                className="control-button"
                onClick={() => handleZoomClick(0.9)}
                title="Zoom Out"
            >
                <ZoomOut />
            </button>
            <button
                className="control-button"
                onClick={() => handleCenterClick()}
                title="Center"
            >
                <Fullscreen />
            </button>
            <button
                className="control-button"
                onClick={() => handleZoomClick(1.1)}
                title="Zoom In"
            >
                <ZoomIn />
            </button>
            <button
                className="hidden md:block control-button"
                title="downloadImage"
                onClick={handleDownloadImage}
            >
                <Download />
            </button>
        </div>
    )
}