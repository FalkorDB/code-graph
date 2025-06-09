import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "@/components/ui/use-toast";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

interface Props {
    options: string[]
    setOptions: (options: string[]) => void
    selectedValue: string
    onSelectedValue: (value: string) => void

}

export default function Combobox({ options, setOptions, selectedValue, onSelectedValue }: Props) {

    const [open, setOpen] = useState(false)
    const [lastFetch, setLastFetch] = useState<number>();
    const [isFetchingOptions, setIsFetchingOptions] = useState(false)

    const fetchOptions = async () => {
        setIsFetchingOptions(true)

        try {
            const result = await fetch(`/api/repo`, {
                method: 'GET',
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
            setOptions(json.result)
        } finally {
            setIsFetchingOptions(false)
        }
    }

    useEffect(() => {
        fetchOptions()
    }, [])

    //fetch options when the combobox is opened
    useEffect(() => {
        if (!open) return

        const now = Date.now();

        //check if last fetch was less than 30 seconds ago
        if (lastFetch && now - lastFetch < 30000) return;
        
        setLastFetch(now);
        
        fetchOptions()
    }, [open])

    return (
        <Select open={open} onOpenChange={setOpen} disabled={options.length === 0 && !isFetchingOptions} value={isFetchingOptions ? "Fetching options..." : options.length !== 0 ? selectedValue : "No options found"} onValueChange={onSelectedValue}>
            <SelectTrigger className="z-10 md:z-0 rounded-md border border-gray-400 md:border-gray-100 focus:ring-0 focus:ring-offset-0">
                <SelectValue placeholder="Select a repo" />
            </SelectTrigger>
            <SelectContent>
                {
                    isFetchingOptions ?
                        <SelectItem value="Fetching options...">
                            <div className="flex flex-row items-center gap-2">
                                <Loader2 className="w-4 h-4 animate-spin" />
                                <p>Fetching options...</p>
                            </div>
                        </SelectItem>
                        : options.length !== 0 ?
                            options.map((option) => (
                                <SelectItem key={option} value={option}>
                                    {option}
                                </SelectItem>
                            ))
                            :
                            <SelectItem value="No options found">
                                <p>No options found</p>
                            </SelectItem>
                }
            </SelectContent>
        </Select>
    )
}