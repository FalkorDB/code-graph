import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card"
import { toast } from "@/components/ui/use-toast"
import { cn } from "@/lib/utils"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { Dispatch, SetStateAction } from "react"
import { Graph } from "./model"

export type CommitChanges = {
    additionsIds: any[]
    modifiedIds: any[]
}
interface Props {
    commitChanges: CommitChanges | undefined
    setCommitChanges: (commitChanges: CommitChanges | undefined) => void
    commits: any[]
    currentCommit: number
    setCurrentCommit: Dispatch<SetStateAction<number>>
    commitIndex: number
    setCommitIndex: Dispatch<SetStateAction<number>>
    graph: Graph,
}

const COMMIT_LIMIT = 7

export default function CommitList({ commitChanges, setCommitChanges, commitIndex, commits, currentCommit, setCommitIndex, setCurrentCommit, graph }: Props) {

    const handelCommitChange = async (commit: any) => {

        const result = await fetch(`api/repo/${graph.Id}/?type=switchCommit`, {
            method: 'POST',
        })

        if (!result.ok) {
            toast({
                title: "Uh oh! Something went wrong",
                description: (await result.text()),
            })
            return
        }

        const json = await result.json()

        json.result.deletions.nodes.forEach((e: any) => {
            graph.NodesMap.delete(e.id)
            graph.Elements.nodes.splice(graph.Elements.nodes.findIndex((el) => el.data.id === e.id), 1)
        })

        json.result.deletions.edges.forEach((e: any) => {
            graph.EdgesMap.delete(e.id)
            graph.Elements.links.splice(graph.Elements.links.findIndex((el) => el.data.id === e.id), 1)
        })

        const additionsIds = graph.extend(json.result.additions).nodes.map((e) => e.id)

        const g = Graph.empty()
        g.extend(json.result.modifications)

        const modifiedIds = [...g.Elements.nodes, ...g.Elements.nodes].map((e) => {
            let graphElement = [...g.Elements.nodes, ...g.Elements.nodes].find((el) => el.data.id === e.data.id)
            graphElement = e

            if ("category" in e) {

            }

            return e.data.id
        })

        setCommitChanges({ additionsIds, modifiedIds })
        setCurrentCommit(commit.hash)
    }

    return (
        <footer className='bg-gray-200 flex border border-gray-300 rounded-b-md'>
            <button
                className='p-4 border-r border-gray-300'
                onClick={() => {
                    setCommitIndex(prev => prev - 1)
                }}
                disabled={commitIndex - COMMIT_LIMIT === 0}
            >
                {
                    commitIndex - COMMIT_LIMIT !== 0 ?
                        <ChevronLeft />
                        : <div className='h-6 w-6' />
                }
            </button>
            <ul className='w-1 grow flex p-3 justify-between gap-4'>
                {
                    commits.slice(commitIndex - COMMIT_LIMIT, commitIndex).map((commit: any) => {
                        const date = new Date(commit.date * 1000)
                        const month = `${date.getDate()} ${date.toLocaleString('default', { month: 'short' })}`
                        const hour = `${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`
                        return (
                            <HoverCard
                                key={commit.hash}
                            >
                                <HoverCardTrigger asChild>
                                    <li
                                        className={cn(currentCommit === commit.hash && "bg-white", "grow p-1 rounded-md")}
                                    >
                                        <button
                                            className='w-full flex items-center justify-center gap-2'
                                            onClick={() => handelCommitChange(commit)}
                                        >
                                            <p title={month}>{month}</p>
                                            <p className='text-gray-400' title='hour'>{hour}</p>
                                        </button>
                                    </li>
                                </HoverCardTrigger>
                                <HoverCardContent className='bg-[#F9F9F9] flex flex-col gap-2 p-4 w-fit max-w-[70%]'>
                                    <h1 className='text-bold'>{commit.author}</h1>
                                    <p>{commit.message}</p>
                                    <p className='text-[#7D7D7D] truncate' title={commit.hash}>{commit.hash}</p>
                                </HoverCardContent>
                            </HoverCard>
                        )
                    })
                }
            </ul>
            <button
                className='p-4 border-l border-gray-300'
                onClick={() => {
                    setCommitIndex(prev => prev + 1)
                }}
                disabled={commitIndex === commits.length}
            >
                {
                    commitIndex !== commits.length ?
                        <ChevronRight />
                        : <div className='h-6 w-6' />
                }
            </button>
        </footer>
    )
}