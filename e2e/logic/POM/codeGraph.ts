import { Locator } from "playwright";
import BasePage from "../../infra/ui/basePage";

export default class CodeGraph extends BasePage {
    /* NavBar Locators*/
    private get homeButton(): Locator {
        return this.page.locator("//a[p[text() = 'Home']]")
    }

    /* CodeGraph Locators*/
    private get comboBoxbtn(): Locator {
        return this.page.locator("//button[@role='combobox']")
    }

    private get selectGraphInComboBox(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']//div[@role='option'][${graph}]`);
    }

    private get lastElementInChat(): Locator {
        return this.page.locator("//main[@data-name='main-chat']/*[last()]/p");
    }

    /* Chat Locators */
    private get showPathBtn(): Locator {
        return this.page.locator("//button[contains(@class, 'Tip')]//div//h1[text()='Show the path']");
    }

    private get askquestionInput(): Locator {
        return this.page.locator("//input[contains(@placeholder, 'Ask your question')]");
    }

    private get askquestionBtn(): Locator {
        return this.page.locator("//input[contains(@placeholder, 'Ask your question')]/following::button[1]");
    }

    private get lightbulbBtn(): Locator {
        return this.page.locator("//button[@data-name='lightbulb']");
    }

    private get lastChatElementButtonCount(): Locator {
        return this.page.locator("//main[@data-name='main-chat']/*[last()]/button");
    }

    private get chatContainer(): Locator {
        return this.page.locator("//main[@data-name='main-chat']");
    }

    private get previousQuestionLoadingImage(): Locator {
        return this.page.locator("//main[@data-name='main-chat']/*[last()-2]//img[@alt='Waiting for response']")
    }
    
    /* NavBar functionality */
    async clickOnHomeBtn(): Promise<void> {
        await this.homeButton.click()
    }

    /* Chat functionality */
    async clickOnshowPathBtn(): Promise<void> {
        await this.showPathBtn.click();
    }

    async sendMessage(message: string) {
        await this.askquestionInput.fill(message);
        await this.askquestionBtn.click();
    }

    async clickOnLightBulbBtn(): Promise<void> {
        await this.lightbulbBtn.click();
    }

    async getTextInLastChatElement(): Promise<string | null>{
        return await this.lastElementInChat.textContent();
    }

    async getLastChatElementButtonCount(): Promise<number | null>{
        return await this.lastChatElementButtonCount.count();
    }

    async scrollToTop() {
        await this.chatContainer.evaluate((chat) => {
          chat.scrollTop = 0;
        });
    }
    
    async getScrollMetrics() {
        const scrollTop = await this.chatContainer.evaluate((el) => el.scrollTop);
        const scrollHeight = await this.chatContainer.evaluate((el) => el.scrollHeight);
        const clientHeight = await this.chatContainer.evaluate((el) => el.clientHeight);
        return { scrollTop, scrollHeight, clientHeight };
    }

    async isAtBottom(): Promise<boolean> {
        const { scrollTop, scrollHeight, clientHeight } = await this.getScrollMetrics();
        return Math.abs(scrollTop + clientHeight - scrollHeight) < 1;
    }

    async getpreviousQuestionLoadingImage(): Promise<boolean> {
        return this.previousQuestionLoadingImage.isVisible();
    }

    /* CodeGraph functionality */
    async selectGraph(graph: string): Promise<void> {
        await this.comboBoxbtn.click();
        await this.selectGraphInComboBox(graph).click();
    }
}