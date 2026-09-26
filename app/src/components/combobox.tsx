import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "@/components/ui/use-toast";
import { useEffect, useState } from "react";
import { RepoOption, repoLabel, toRepoOption } from "@/lib/utils";

const AUTH_HEADERS: HeadersInit = import.meta.env.VITE_SECRET_TOKEN
  ? { 'Authorization': `Bearer ${import.meta.env.VITE_SECRET_TOKEN}` }
  : {};

interface Props {
    options: RepoOption[]
    setOptions: (options: RepoOption[]) => void
    selectedValue: string
    onSelectedValue: (value: string) => Promise<void>

}

export default function Combobox({ options, setOptions, selectedValue, onSelectedValue }: Props) {

    const [open, setOpen] = useState(false)
    const [lastOpened, setLastOpened] = useState<number>();

    const fetchOptions = async () => {
        const result = await fetch(`/api/list_repos`, {
            method: 'GET',
            headers: {
                ...AUTH_HEADERS,
            },
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
        const repositories: unknown[] = Array.isArray(json.repositories) ? json.repositories : []
        setOptions(repositories.map(toRepoOption))
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
            <SelectTrigger className="z-10 -mx-2 w-[calc(100%+1rem)] rounded-md border border-border focus:ring-1 focus:ring-primary md:z-0 md:mx-0 md:w-full">
                <SelectValue placeholder="Select a repo" />
            </SelectTrigger>
            <SelectContent className="max-w-[calc(100vw-1rem)]">
                {
                    options.length !== 0 &&
                    options.map((option) => (
                        <SelectItem key={option.graph} value={option.graph}>
                            {repoLabel(option)}
                        </SelectItem>
                    ))
                }
            </SelectContent>
        </Select>
    )
}