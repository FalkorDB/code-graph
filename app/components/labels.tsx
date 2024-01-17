import { Category, getCategoryColorName} from "./model";
import { cn } from "@/lib/utils";
import { Minus, Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";

export function Labels(params: { categories: Category[], className?: string, onClick: (category: Category) => void }) {

    // fake stae to force reload
    const [reload, setReload] = useState(false)

    return (
        <div className={cn("flex flex-row gap-x-2", params.className)} >
            {params.categories.map((category) => {
                return (
                    <div className="flex flex-row gap-x-2 items-center" key={category.index}>
                        <Button
                            className={cn(`bg-${getCategoryColorName(category.index)}-500 ${category.show ? "" : "opacity-50"}`, "rounded-lg border border-gray-300 p-2 opac")}
                            onClick={() => {
                                params.onClick(category)
                                setReload(!reload)
                            }}
                        >
                            {category.show ? <Minus /> : <Plus />}
                        </Button>
                        <p>{category.name}</p>
                    </div>
                )
            })}
        </div>
    )
}