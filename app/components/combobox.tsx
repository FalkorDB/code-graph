import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

interface Props {
    options: string[]
    selectedValue: string
    onSelectedValue: (value: string) => void

}

export default function Combobox({ options, selectedValue, onSelectedValue }: Props) {
    return (
        <Select value={selectedValue} onValueChange={onSelectedValue}>
            <SelectTrigger className="rounded-md border focus:ring-0 focus:ring-offset-0">
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