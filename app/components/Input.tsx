import { toast } from "@/components/ui/use-toast"
import { getCategoryColorName, getCategoryColorValue, Graph } from "./model"
import { useEffect, useRef, useState } from "react"
import { PathNode } from "../page"
import { cn } from "@/lib/utils"
import { prepareArg } from "../utils"

interface Props extends React.InputHTMLAttributes<HTMLInputElement> {
    graph: Graph
    onValueChange: (node: PathNode) => void
    handleSubmit?: (node: any) => void
    icon?: React.ReactNode
    node?: PathNode
    parentClassName?: string
    scrollToBottom?: () => void
}

export default function Input({ onValueChange, handleSubmit, graph, icon, node, className, parentClassName, scrollToBottom, ...props }: Props) {

    const [open, setOpen] = useState(false)
    const [options, setOptions] = useState<any[]>([])
    const [selectedOption, setSelectedOption] = useState<number>(0)
    const [inputHeight, setInputHeight] = useState(0)
    const containerRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        setSelectedOption(0)

        if (open) {
            scrollToBottom && scrollToBottom()
        }
    }, [open])

    useEffect(() => {
        if (!graph.Id) return

        let isLastRequest = true
        const timeout = setTimeout(async () => {

            if (!node?.name) {
                setOptions([])
                setOpen(false)
                return
            }

            const result = await fetch(`/api/repo/${prepareArg(graph.Id)}/?prefix=${prepareArg(node?.name)}`, {
                method: 'POST'
            })

            if (!result.ok) {
                toast({
                    variant: "destructive",
                    title: "Uh oh! Something went wrong.",
                    description: "Please try again later.",
                })
                return
            }

            if (!isLastRequest) return

            const json = await result.json()
            const { completions } = json.result

            setOptions(completions || [])

            if (completions?.length > 0 && !node?.id) {
                setOpen(true)
            } else {
                setOpen(false)
            }
        }, 500)

        return () => {
            clearTimeout(timeout)
            isLastRequest = false
        }
    }, [node?.name, graph.Id])

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        const container = containerRef.current
        switch (e.code) {
            case "Enter": {
                e.preventDefault()
                const option = options.find((o, i) => i === selectedOption)
                if (!option) return
                if (handleSubmit) {
                    onValueChange({ name: option.properties.name, id: option.id })
                    handleSubmit(option)
                } else {
                    if (!open) return
                    onValueChange({ name: option.properties.name, id: option.id })
                }
                setOpen(false)
                return
            }
            case "ArrowUp": {
                e.preventDefault()
                setSelectedOption(prev => {
                    const newIndex = prev <= 0 ? options.length - 1 : prev - 1
                    if (container) {
                        container.scrollTo({ behavior: 'smooth', top: 64 * newIndex })
                    }
                    return newIndex
                })
                return
            }
            case "ArrowDown": {
                e.preventDefault()
                setSelectedOption(prev => {
                    const newIndex = (prev + 1) % options.length
                    if (container) {
                        container.scrollTo({ behavior: 'smooth', top: Math.min(64 * newIndex, container.scrollHeight) })
                    }
                    return newIndex
                })
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
            className={cn("w-[20dvw] relative pointer-events-none rounded-md gap-4", parentClassName)}
            data-name='search-bar'
        >
            <input
                ref={ref => {
                    if (ref) {
                        setInputHeight(ref.scrollHeight)
                    }
                }}
                onKeyDown={handleKeyDown}
                className={cn("w-full border p-2 rounded-md pointer-events-auto", className)}
                value={node?.name || ""}
                onChange={(e) => {
                    const newVal = e.target.value
                    const invalidChars = /[%*()\-\[\]{};:"|~]/;

                    if (invalidChars.test(newVal)) {
                        e.target.setCustomValidity(`The character "${newVal.match(invalidChars)?.[0]}" is not allowed in this field.`);
                        e.target.reportValidity();
                        return;
                    }
                    e.target.setCustomValidity('');
                    onValueChange({ name: newVal })
                }}
                {...props}
                onBlur={(e) => {
                    if (!containerRef.current?.contains(e.relatedTarget as Node)) {
                        setOpen(false)
                    }
                }}
            />
            {
                open &&
                <div
                    ref={containerRef}
                    className="z-10 w-full bg-white absolute flex flex-col pointer-events-auto border rounded-md max-h-[50dvh] overflow-y-auto overflow-x-hidden p-2 gap-2"
                    data-name='search-bar-list'
                    style={{
                        top: inputHeight + 16
                    }}
                >
                    {
                        options.length > 0 &&
                        options.map((option, index) => {
                            const label = option.labels[0]
                            const name = option.properties.name
                            const path = option.properties.path
                            let category = graph.CategoriesMap.get(label)

                            if (!category) {
                                category = { name: label, index: graph.CategoriesMap.size, show: true }
                                graph.CategoriesMap.set(label, category)
                                graph.Categories.push(category)
                            }

                            const colorName = getCategoryColorName(category.index)
                            const color = getCategoryColorValue(category.index)
                            return (
                                <button
                                    className={cn(
                                        "w-full flex gap-3 p-1 items-center rounded-md",
                                        selectedOption === index && "bg-gray-100"
                                    )}
                                    onMouseEnter={() => setSelectedOption(index)}
                                    onClick={() => {
                                        onValueChange({ name: option.properties.name, id: option.id })
                                        handleSubmit && handleSubmit(option)
                                        setOpen(false)
                                    }}
                                    key={option.id}
                                >
                                    <p className={`truncate w-[30%] bg-${colorName} bg-opacity-20 p-1 rounded-md`} style={{ color }} title={label}>{label}</p>
                                    <div className="w-1 grow text-start">
                                        <p className="truncate" title={name}>
                                            {name}
                                        </p>
                                        <p className="truncate p-1 text-xs font-medium text-gray-400" title={path}>
                                            {path}
                                        </p>
                                    </div>
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