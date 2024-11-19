import { Locator, Page } from "playwright";
import BasePage from "../../infra/ui/basePage";
import { delay } from "../utils";

export default class CodeGraph extends BasePage {
    /* NavBar Locators*/
    private get falkorDBLogo(): Locator {
        return this.page.locator("//*[img[@alt='FalkorDB']]")
    }

    private get navBaritem(): (navItem: string) => Locator {
        return (navItem: string) => this.page.locator(`//a[p[text() = '${navItem}']]`);
    }

    private get createNewProjectBtn(): Locator {
        return this.page.getByRole('button', { name: 'Create new project' });
    }

    private get createNewProjectDialog(): Locator {
        return this.page.locator("//div[@role='dialog']")
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
        return this.page.locator("//button[contains(@class, 'Tip')]");
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

    private get selectInputForShowPath(): (inputNum: string) => Locator {
        return (inputNum: string) => this.page.locator(`(//main[@data-name='main-chat']//input)[${inputNum}]`);
    }

    private get locateNodeInLastChatPath(): (node: string) => Locator {
        return (node: string) => this.page.locator(`//main[@data-name='main-chat']/*[last()]//span[contains(text(), '${node}')]`);
    }

    private get selectFirstPathOption(): (inputNum: string) => Locator {
        return (inputNum: string) => this.page.locator(`(//main[@data-name='main-chat']//input)[1]/following::div[${inputNum}]//button[1]`);
    }

    private get notificationNoPathFound(): Locator {
        return this.page.locator("//div//ol/li");
    }
    
    /* NavBar functionality */
    async clickOnFalkorDbLogo(): Promise<Page> {
        await this.page.waitForLoadState('networkidle'); 
        const [newPage] = await Promise.all([
            this.page.waitForEvent('popup'),
            this.falkorDBLogo.click(),
        ]);
        return newPage
    }

    async getNavBarItem(navItem : string): Promise<Page> {
        await this.page.waitForLoadState('networkidle'); 
        const [newPage] = await Promise.all([
            this.page.waitForEvent('popup'),
            this.navBaritem(navItem).click(),
        ]);
        return newPage
    }

    async clickCreateNewProjectBtn(): Promise<void> {
        await this.createNewProjectBtn.click();
    }

    async isCreateNewProjectDialog(): Promise<boolean> {
        return await this.createNewProjectDialog.isVisible();
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

    async insertInputForShowPath(inputNum: string, node: string): Promise<void> {
        await this.selectInputForShowPath(inputNum).fill(node);
        await this.selectFirstPathOption(inputNum).click();
    }

    async isNodeVisibleInLastChatPath(node: string): Promise<boolean> {
        return await this.locateNodeInLastChatPath(node).isVisible();
    }

    async isNotificationNoPathFound(): Promise<boolean> {
        return await this.notificationNoPathFound.isVisible();
    }

    /* CodeGraph functionality */
    async selectGraph(graph: string): Promise<void> {
        await this.comboBoxbtn.click();
        await this.selectGraphInComboBox(graph).waitFor({ state : 'visible'})
        await this.selectGraphInComboBox(graph).click();
    }
}
