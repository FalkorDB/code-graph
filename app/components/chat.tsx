import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/use-toast";
import { useEffect, useRef, useState } from "react";
import { QUESTIONS } from "../api/repo/questions";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import Image from "next/image";
import { SendHorizonal } from "lucide-react";

enum MessageTypes {
    Query,
    Response,
    Pending,
}

interface Message {
    text: string;
    type: MessageTypes;
}

export function Chat(props: { repo: string }) {

    // Holds the messages in the chat
    const [messages, setMessages] = useState<Message[]>([]);

    // Holds the user input while typing
    const [query, setQuery] = useState('');

    // A reference to the chat container to allow scrolling to the bottom
    const bottomRef: React.RefObject<HTMLDivElement> = useRef(null);

    // A function that handles the change event of the url input box
    async function handleQueryInputChange(event: any) {

        if (event.key === "Enter") {
            await handleQueryClick(event);
        }

        // Get the new value of the input box
        const value = event.target.value;

        // Update the url state
        setQuery(value);
    }

    // Send the user query to the server
    async function sendQuery(q: string) {
        if (!q) {
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: "Please enter a question.",
            })
            setQuery("")
            return
        }

        setMessages((messages) => [...messages, { text: q, type: MessageTypes.Query }, { text: "", type: MessageTypes.Pending }]);

        return fetch(`/api/repo/${props.repo}?q=${encodeURIComponent(q)}&type=text`, {
            method: 'GET'
        }).then(async (result) => {
            if (result.status >= 300) {
                throw Error(await result.text())

            }

            return result.json()
        }).then(data => {
            // Create an array of messages from the current messages remove the last pending message and add the new response
            setMessages(function (messages) {
                if (messages[messages.length - 1].type === MessageTypes.Pending) {
                    // Remove the last pending message if exists
                    messages = messages.slice(0, -1);
                }
                return [...messages, { text: data.result, type: MessageTypes.Response }];
            });
            setQuery("")
        }).catch((error) => {
            setMessages(function (messages) {
                if (messages[messages.length - 1].type === MessageTypes.Pending) {
                    // Remove the last pending message if exists
                    return messages.slice(0, -1);
                }
                return messages
            });
            setQuery("")
            toast({
                variant: "destructive",
                title: "Uh oh! Something went wrong.",
                description: error.message,
            });
        });
    }

    // A function that handles the click event
    async function handleQueryClick(event: any) {
        event.preventDefault();
        return sendQuery(query.trim());
    }

    // On question selected from the predefined questions list
    async function onQuestionSelected(value: string) {
        setQuery(value)
        return sendQuery(value)
    }

    // Scroll to the bottom of the chat on new message
    useEffect(() => {
        bottomRef.current?.scrollTo(0, bottomRef.current?.scrollHeight);
    }, [messages]);

    return (
        <>
            <header className="bg-black flex gap-4 items-center p-6 text-white">
                <Image src="falkordb-circle.svg" alt="" height={30} width={30} />
                <h1>Set your query</h1>
            </header>
            <main ref={bottomRef} className="p-4 flex-1 space-y-4 overflow-auto">
                {
                    messages.map((message, index) => {
                        if (message.type === MessageTypes.Query) {
                            return (<div key={index} className="flex gap-2 items-center">
                                <div className="h-6 w-6 rounded-full overflow-hidden">
                                    <Image src="falkordb-circle.svg" alt="" height={24} width={24} />
                                </div>
                                <p className="text-sm">{message.text}</p>
                            </div>)
                        } else if (message.type === MessageTypes.Response) {
                            return (<div key={index} className="flex gap-2 items-center">
                                <div className="h-6 w-6 rounded-full overflow-hidden">
                                    <Image src="falkordb-circle.svg" alt="" height={24} width={24} />
                                </div>
                                <p className="text-sm">{message.text}</p>
                            </div>)
                        } else {
                            return (<div key={index} className="flex gap-2">
                                <div>
                                    <Image src="/dots.gif" width={100} height={10} alt="Waiting for response" />
                                </div>
                            </div>)
                        }
                    })
                }
            </main>
            <footer className="p-8">
                {props.repo &&
                    <form className="relative" onSubmit={handleQueryClick}>
                        {/* <Select onValueChange={onQuestionSelected}>
                            <SelectTrigger className="w-1/3">
                                <SelectValue placeholder="Suggested questions" />
                            </SelectTrigger>
                            <SelectContent>
                                {
                                    QUESTIONS.map((question, index) => {
                                        return <SelectItem key={index} value={question}>{question}</SelectItem>
                                    })
                                }
                            </SelectContent>
                        </Select> */}
                        <Input className="p-6 rounded-2xl bg-gray-100 focus-visible:ring-0 focus-visible:ring-offset-0" placeholder="Enter a prompt here" onChange={handleQueryInputChange} value={query} />
                        <button className="absolute top-4 right-2">
                            <SendHorizonal />
                        </button>
                    </form>
                }
            </footer>
        </>
    );
}
