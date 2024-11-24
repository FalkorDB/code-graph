import { Position } from "cytoscape";
import { useState } from "react";

interface Props {
    label: string | undefined;
    position: Position | undefined;
    parentWidth: number;
}

export default function ElementTooltip({ label, position, parentWidth }: Props) {
    const [containerWidth, setContainerWidth] = useState<number>(0);

    if (!label || !position) return null

    return (
        <div
            ref={(ref) => {
                if (!ref) return
                setContainerWidth(ref.clientWidth)
            }}
            className="absolute z-20 bg-white rounded-lg shadow-lg p-3"
            style={{
                left: Math.max(-34, Math.min(position.x - containerWidth / 2, parentWidth + 34 - containerWidth)),
                top: position.y
            }}
        >
            {label}
        </div>
    )
}