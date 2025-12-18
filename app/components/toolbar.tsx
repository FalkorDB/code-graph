import { Download, Fullscreen, ZoomIn, ZoomOut } from "lucide-react";
import { cn } from "@/lib/utils"
import { GraphRef } from "@/lib/utils";

interface Props {
    canvasRef: GraphRef
    className?: string
    handleDownloadImage?: () => void
}

export function Toolbar({ canvasRef, className, handleDownloadImage }: Props) {

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
        <div className={cn("flex flex-row rounded overflow-hidden p-1", className)}>
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