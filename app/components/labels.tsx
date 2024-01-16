import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Category, getCategoryColors } from "./model";
import { cn } from "@/lib/utils";
import { MinusCircle, Palette, PlusCircle } from "lucide-react";
import { useState } from "react";

export function Labels(params: { categories: Category[], className?: string, onClick: (category: Category) => void }) {

    // fake stae to force reload
    const [reload, setReload] = useState(false)

    return (
        <div className={cn("flex flex-row", params.className)} >
            <TooltipProvider>
                {params.categories.map((category) => {
                    return (
                        <Tooltip key={category.index}>
                            <TooltipTrigger
                                className={`bg-${getCategoryColors(category.index)}-${category.show ? 500 : 200} rounded-lg border border-gray-300 p-2`}
                                onClick={() => {
                                    params.onClick(category)
                                    setReload(!reload)
                                }}
                            >
                                { category.show ? <MinusCircle /> : <PlusCircle /> }
                            </TooltipTrigger>
                            <TooltipContent>
                                <p>{category.name}</p>
                            </TooltipContent>
                        </Tooltip>
                    )
                })}
            </TooltipProvider>
        </div>
    )
}