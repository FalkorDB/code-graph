interface Logger {
    log(message: string): void;
}

class ConsoleLogger implements Logger {
    private prefix: string;

    constructor(prefix: string) {
        this.prefix = prefix;
    }

    log(message: string): void {
        console.log(`${this.prefix}: ${message}`);
    }
}

function greet(name: string): string {
    const logger = new ConsoleLogger("App");
    logger.log(`Hello ${name}`);
    return `Hello, ${name}!`;
}
