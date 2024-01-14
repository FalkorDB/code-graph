import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/use-toast";
import { useEffect, useRef, useState } from "react";
import { QUESTIONS } from "../api/repo/questions";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import Image from "next/image";

const LIMITED_MODE = process.env.NEXT_PUBLIC_MODE?.toLowerCase()==='limited';

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
            setMessages(function(messages) {
                if(messages[messages.length - 1].type === MessageTypes.Pending){
                    // Remove the last pending message if exists
                    messages = messages.slice(0, -1); 
                } 
                return [...messages, { text: data.result, type: MessageTypes.Response }];
            });
        }).catch((error) => {
            setMessages(function(messages) {
                if(messages[messages.length - 1].type === MessageTypes.Pending){
                    // Remove the last pending message if exists
                    return messages.slice(0, -1);
                }
                return messages
            });
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
        return sendQuery(query);
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
            <main ref={bottomRef} className="border p-4 flex-1 space-y-4 overflow-auto">
                {
                    messages.map((message, index) => {
                        if (message.type === MessageTypes.Query) {
                            return (<div key={index} className="flex items-end gap-2">
                                <div className="rounded-lg bg-zinc-200 dark:bg-zinc-700 p-2">
                                    <p className="text-sm">{message.text}</p>
                                </div>
                            </div>)
                        } else if (message.type === MessageTypes.Response) {
                            return (<div key={index} className="flex items-end gap-2 justify-end">
                                <div className="rounded-lg bg-blue-500 text-white p-2">
                                    <p className="text-sm">{message.text}</p>
                                </div>
                            </div>)
                        } else {
                            return (<div key={index} className="flex items-end gap-2 justify-end">
                                <div>
                                    <Image src="/dots.gif" width={100} height={10} alt="Waiting for response"/>
                                </div>
                            </div>)
                        }
                    })
                }
            </main>
            <footer className="border p-4">
            {props.repo &&
                <form className="flex flex-row gap-2" onSubmit={handleQueryClick}>
                    <Select onValueChange={onQuestionSelected}>
                        <SelectTrigger className="min-w-1/3">
                            <SelectValue placeholder="Suggested questions" />
                        </SelectTrigger>
                        <SelectContent>
                            {
                                QUESTIONS.map((question, index) => {
                                    return <SelectItem key={index} value={question}>{question}</SelectItem>
                                })
                            }
                        </SelectContent>
                    </Select>
                    {
                        !LIMITED_MODE && <Input className="w-2/3" placeholder="Type a question..." onChange={handleQueryInputChange} />
                    }
                    <Button>Send</Button>
                </form>
            }
            </footer>
        </>
    );
}
