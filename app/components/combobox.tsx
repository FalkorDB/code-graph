import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "@/components/ui/use-toast";
import { useEffect, useState } from "react";

interface Props {
    options: string[]
    setOptions: (options: string[]) => void
    selectedValue: string
    onSelectedValue: (value: string) => void

}

export default function Combobox({ options, setOptions, selectedValue, onSelectedValue }: Props) {

    const [open, setOpen] = useState(false)
    const [lastOpened, setLastOpened] = useState<number>();

    const fetchOptions = async () => {
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
    }

    useEffect(() => {
        fetchOptions()
    }, [])

    useEffect(() => {
        if (!open) return

        const now = Date.now();

        if (lastOpened && now - lastOpened < 30000) return;

        setLastOpened(now);

        fetchOptions()
    }, [open])

    return (
        <Select open={open} onOpenChange={setOpen} value={selectedValue} onValueChange={onSelectedValue}>
            <SelectTrigger className="z-10 md:z-0 rounded-md border border-gray-400 md:border-gray-100 focus:ring-0 focus:ring-offset-0">
                <SelectValue placeholder="Select a repo" />
            </SelectTrigger>
            <SelectContent>
                {
                    options.length !== 0 &&
                    options.map((option) => (
                        <SelectItem key={option} value={option}>
                            {option}
                        </SelectItem>
                    ))
                }
            </SelectContent>
        </Select>
    )
}