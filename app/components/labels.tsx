import { Category, getCategoryColorName } from "./model";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { useState } from "react";

export function Labels(params: { categories: Category[], className?: string, onClick: (name: string, show: boolean) => void }) {

    const [reload, setReload] = useState(false)

    return (
        <div className={cn("flex gap-4", params.className)} >
            {params.categories.map((category) =>
                <div className="bg-white flex gap-2 items-center p-2 border rounded-md pointer-events-auto" key={category.index}>
                    <Checkbox
                        className={`data-[state=checked]:bg-${getCategoryColorName(category.index)} bg-${getCategoryColorName(category.index)} border-none rounded-sm`}
                        onCheckedChange={(checked) => {
                            params.onClick(category.name, checked as boolean)
                            setReload(!reload)
                        }}
                        checked={category.show}
                    />
                    <p>{category.name}</p>
                </div>
            )
            }
        </div >
    )
}