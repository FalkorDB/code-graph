import { Locator, Page } from "playwright";
import BasePage from "../../infra/ui/basePage";
import { delay, waitToBeEnabled } from "../utils";
import { analyzeCanvasWithLocator, CanvasAnalysisResult } from "../canvasAnalysis";

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

    private get typeUrlInput(): Locator {
        return this.page.locator("//div[@role='dialog']/form/input");
    }

    private get createBtnInCreateProjectDialog(): Locator {
        return this.page.locator("//div[@role='dialog']/form//following::button//p[contains(text(), 'Create')]")
    }

    private get createProjectWaitDialog(): Locator {
        return this.page.locator("//div[@role='dialog']//div//h2[contains(text(), 'THANK YOU FOR A NEW REQUEST')]")
    }

    private get dialogCreatedGraphsList(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']/div//span[2][contains(text(), '${graph}')]`);
    }

    private get searchBarInput(): Locator {
        return this.page.locator("//div[@data-name='search-bar']/input");
    }

    private get searchBarAutoCompleteOptions(): Locator {
        return this.page.locator("//div[@data-name='search-bar']/div/button");
    }

    private get searchBarElements(): Locator {
        return this.page.locator("//div[@data-name='search-bar']/div/button/div/p[1]");
    }

    private get searchBarOptionBtn(): (buttonNum: string) => Locator {
        return (buttonNum: string) => this.page.locator(`//div[@data-name='search-bar']//button[${buttonNum}]`);
    }

    private get searchBarList(): Locator {
        return this.page.locator("//div[@data-name='search-bar-list']");
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

    private get notificationError(): Locator {
        return this.page.locator("//div[@role='region']//ol//li");
    }

    /* Canvas Locators*/

    private get canvasElement(): Locator {
        return this.page.locator("//canvas[position()=3]");
    }

    private get zoomInBtn(): Locator {
        return this.page.locator("//button[@title='Zoom In']");
    }

    private get zoomOutBtn(): Locator {
        return this.page.locator("//button[@title='Zoom Out']");
    }

    private get centerBtn(): Locator {
        return this.page.locator("//button[@title='Center']");
    }

    private get removeNodeViaElementMenu(): Locator {
        return this.page.locator("//button[@title='Remove']");
    }

    private get codeGraphCheckbox(): (checkbox: string) => Locator {
        return (checkbox: string) => this.page.locator(`(//button[@role='checkbox'])[${checkbox}]`);
    }

    private get clearGraphBtn(): Locator {
        return this.page.locator("//button[p[text()='Clear Graph']]");
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
    
    async clickAskquestionBtn(): Promise<void> {
        await this.askquestionBtn.click();
    }

    async sendMessage(message: string) {
        await waitToBeEnabled(this.askquestionInput);
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
        await this.locateNodeInLastChatPath(node).waitFor({ state: 'visible' }); 
        return await this.locateNodeInLastChatPath(node).isVisible();
    }

    async isNotificationError(): Promise<boolean> {
        return await this.notificationError.isVisible();
    }

    /* CodeGraph functionality */
    async selectGraph(graph: string): Promise<void> {
        await this.comboBoxbtn.click();
        await this.selectGraphInComboBox(graph).waitFor({ state : 'visible'})
        await this.selectGraphInComboBox(graph).click();
    }

    async createProject(url : string): Promise<void> {
        await this.clickCreateNewProjectBtn();
        await this.typeUrlInput.fill(url);
        await this.createBtnInCreateProjectDialog.click();
        await this.createProjectWaitDialog.waitFor({ state : 'hidden'});
    }

    async isGraphCreated(graph: string): Promise<boolean> {
        await this.comboBoxbtn.click();
        return await this.dialogCreatedGraphsList(graph).isVisible();
    }

    async fillSearchBar(searchValue: string): Promise<void> {
        await this.searchBarInput.fill(searchValue);
    }

    async getSearchAutoCompleteCount(): Promise<number> {
        return await this.searchBarAutoCompleteOptions.count();
    }

    async getSearchBarElementsText(): Promise<string[]> {
        return await this.searchBarElements.allTextContents();
    }

    async selectSearchBarOptionBtn(buttonNum: string): Promise<void> {
        await this.searchBarOptionBtn(buttonNum).click();
    }

    async getSearchBarInputValue(): Promise<string> {
        return await this.searchBarInput.inputValue();
    }
    
    async scrollToBottomInSearchBarList(): Promise<void> {
        await this.searchBarList.evaluate((element) => {
          element.scrollTop = element.scrollHeight;
    })};

    async isScrolledToBottomInSearchBarList(): Promise<boolean> {
        return await this.searchBarList.evaluate((element) => {
          return element.scrollTop + element.clientHeight >= element.scrollHeight;
        });
    }

    /* Canvas functionality */

    async getCanvasAnalysis(): Promise<CanvasAnalysisResult> {
        await delay(2000);
        return await analyzeCanvasWithLocator(this.canvasElement);
    }

    async clickZoomIn(): Promise<void> {
        await this.zoomInBtn.click();
    }

    async clickZoomOut(): Promise<void> {
        await this.zoomOutBtn.click();
    }

    async clickCenter(): Promise<void> {
        await this.centerBtn.click();
    }

    async clickOnRemoveNodeViaElementMenu(): Promise<void> {
        await this.removeNodeViaElementMenu.click();
    }

    async rightClickOnNode(x : number, y: number): Promise<void> {
        const boundingBox = (await this.canvasElement.boundingBox())!;
        const adjustedX = boundingBox.x + Math.round(x);
        const adjustedY = boundingBox.y + Math.round(y);
        await this.page.mouse.click(adjustedX, adjustedY, { button: 'right' });
    }

    async selectCodeGraphCheckbox(checkbox: string): Promise<void> {
        await this.codeGraphCheckbox(checkbox).click();
    }

    async clickOnClearGraphBtn(): Promise<void> {
        await this.clearGraphBtn.click();
    } 
}
