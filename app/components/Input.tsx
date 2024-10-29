import { toast } from "@/components/ui/use-toast"
import { getCategoryColorName, Graph } from "./model"
import { useEffect, useRef, useState } from "react"
import { PathNode } from "../page"
import { cn } from "@/lib/utils"

interface Props extends React.InputHTMLAttributes<HTMLInputElement> {
    value?: string
    graph: Graph
    onValueChange: (node: PathNode) => void
    handelSubmit?: (node: any) => void
    icon?: React.ReactNode
    node?: PathNode
    parentClassName?: string
}

export default function Input({ value, onValueChange, handelSubmit, graph, icon, node, className, parentClassName, ...props }: Props) {

    const [open, setOpen] = useState(false)
    const [options, setOptions] = useState<any[]>([])
    const [selectedOption, setSelectedOption] = useState<number>(0)
    const inputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        setSelectedOption(0)
    }, [open])

    useEffect(() => {
        const timeout = setTimeout(async () => {

            if (!value || node?.id) return

            const result = await fetch(`/api/repo/${graph.Id}/?prefix=${value}&type=autoComplete`, {
                method: 'POST'
            })

            if (!result.ok) {
                toast({
                    variant: "destructive",
                    title: "Uh oh! Something went wrong.",
                    description: await result.text(),
                })
                return
            }

            const json = await result.json()

            const { completions } = json.result
            setOptions(completions)
            setOpen(true)
            setTimeout(() => {
                inputRef?.current?.focus();
            }, 0);
        }, 500)

        return () => clearTimeout(timeout)
    }, [value])

    const handelKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        switch (e.code) {
            case "Enter": {
                e.preventDefault()
                const option = options.find((o, i) => i === selectedOption)
                onValueChange({ name: option.properties.name, id: option.id })
                handelSubmit && handelSubmit(option)
                setOpen(false)
                return
            }
            case "ArrowUp": {
                e.preventDefault()
                console.log(selectedOption <= 0 ? selectedOption : selectedOption - 1);
                setSelectedOption(prev => prev <= 0 ? options.length - 1 : prev - 1)
                return
            }
            case "ArrowDown": {
                e.preventDefault()
                setSelectedOption(prev => (prev + 1) % options.length)
                return
            }
            case "Space": {
                if (e.ctrlKey) {
                    e.preventDefault()
                    setOpen(true)
                }
                return
            }
            case "Escape": {
                e.preventDefault()
                setOpen(false)
            }
        }
    }

    return (
        <div
            className={cn("w-[30%] relative pointer-events-none rounded-md gap-4", parentClassName)}
        >
            <input
                ref={inputRef}
                onKeyDown={handelKeyDown}
                className={cn("w-full border p-2 rounded-md pointer-events-auto", className)}
                value={value || ""}
                onChange={(e) => {
                    const newVal = e.target.value
                    onValueChange({ name: newVal })
                }}
                {...props}
            />
            {
                open &&
                <div
                    className="z-10 w-full bg-white absolute flex flex-col pointer-events-auto border rounded-md max-h-[50dvh] overflow-auto p-2 gap-2"
                    style={{
                        top: (inputRef.current?.clientHeight || 0) + 16
                    }}
                >
                    {
                        options.map((option, index) => {
                            const label = option.labels[0]
                            const color = getCategoryColorName(graph.CategoriesMap.get(label)?.index)
                            return (
                                <button
                                    className={cn(
                                        "w-full flex gap-4 p-1 items-center rounded-md",
                                        selectedOption === index && "bg-gray-100"
                                    )}
                                    onMouseEnter={() => setSelectedOption(index)}
                                    onMouseLeave={() => setSelectedOption(-1)}
                                    onClick={() => {
                                        onValueChange({ name: option.properties.name, id: option.id })
                                        handelSubmit && handelSubmit(option)
                                        setOpen(false)
                                    }}
                                    key={option.id}
                                >
                                    <div className={`w-[20%] bg-${color}-500 text-xs text-${color}-500 bg-opacity-20 p-1 rounded-md`}>
                                        <p>{label}</p>
                                    </div>
                                    <p>
                                        {option.properties.name}
                                    </p>
                                </button>
                            )
                        })
                    }
                </div>
            }
            <div className='absolute top-2 right-3' >
                {icon}
            </div>
        </div>
    )
}