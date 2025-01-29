import { Locator, Page } from "playwright";
import BasePage from "../../infra/ui/basePage";
import { delay, waitToBeEnabled } from "../utils";

declare global {
    interface Window {
        graph: any;
    }
}

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

    private get tipBtn(): Locator {
        return this.page.locator("//button[@title='Tip']")
    }

    private get genericMenu(): Locator {
        return this.page.locator("//div[contains(@role, 'menu')]")
    }

    private get tipMenuCloseBtn(): Locator {
        return this.page.locator("//div[@role='menu']//button[@title='Close']")
    }

    /* CodeGraph Locators*/
    private get comboBoxbtn(): Locator {
        return this.page.locator("//button[@role='combobox']")
    }

    private get selectGraphInComboBoxByName(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']//div//span[contains(text(), '${graph}')]`);
    }

    private get selectGraphInComboBoxById(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']//div[${graph}]`);
    }

    private get lastElementInChat(): Locator {
        return this.page.locator("//main[@data-name='main-chat']/*[last()]/span");
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
        return (node: string) => this.page.locator(`(//main[@data-name='main-chat']//span[contains(text(), '${node}')])[last()]`);
    }

    private get selectFirstPathOption(): (inputNum: string) => Locator {
        return (inputNum: string) => this.page.locator(`(//main[@data-name='main-chat']//input)[1]/following::div[${inputNum}]//button[1]`);
    }

    private get notificationError(): Locator {
        return this.page.locator("//div[@role='region']//ol//li");
    }

    private get notificationErrorCloseBtn(): Locator {
        return this.page.locator("//div[@role='region']//ol//li/button");
    }

    private get questionOptionsMenu(): Locator {
        return this.page.locator("//button[@data-name='questionOptionsMenu']");
    }

    private get selectQuestionInMenu(): (questionNumber: string) => Locator {
        return (questionNumber: string) => this.page.locator(`//div[contains(@role, 'menu')]/button[${questionNumber}]`);
    }

    private get lastQuestionInChat(): Locator {
        return this.page.locator("//main[@data-name='main-chat']/*[last()-1]/p");
    }

    private get responseLoadingImg(): Locator {
        return this.page.locator("//img[@alt='Waiting for response']");
    }

    /* Canvas Locators*/

    private get canvasElement(): Locator {
        return this.page.locator("//canvas");
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

    private get codeGraphCheckbox(): (checkbox: string) => Locator {
        return (checkbox: string) => this.page.locator(`(//button[@role='checkbox'])[${checkbox}]`);
    }

    private get clearGraphBtn(): Locator {
        return this.page.locator("//button[p[text()='Reset Graph']]");
    }

    private get unhideNodesBtn(): Locator {
        return this.page.locator("//button[p[text()='Unhide Nodes']]");
    }

    private get elementMenuButton(): (buttonID: string) => Locator {
        return (buttonID: string) => this.page.locator(`//button[@title='${buttonID}']`);
    }

    private get nodeDetailsPanel(): Locator {
        return this.page.locator("//div[@data-name='node-details-panel']");
    }
    
    private get nodedetailsPanelHeader(): Locator {
        return this.page.locator("//div[@data-name='node-details-panel']/header/p");
    }
    
    private get nodedetailsPanelcloseBtn(): Locator {
        return this.page.locator("//div[@data-name='node-details-panel']/header/button");
    }
    private get canvasMetricsPanel(): (itemId: string) => Locator {
        return (itemId: string) => this.page.locator(`//div[@data-name='metrics-panel']/p[${itemId}]`);
    }

    private get nodedetailsPanelID(): Locator {
        return this.page.locator("//div[@data-name='node-details-panel']/main/div[1]/p[2]");
    }

    private get nodedetailsPanelElements(): Locator {
        return this.page.locator("//div[@data-name='node-details-panel']/main/div/p[1]");
    }

    private get canvasElementBeforeGraphSelection(): Locator {
        return this.page.locator("//h1[contains(text(), 'Select a repo to show its graph here')]");
    }

    private get copyToClipboardNodePanelDetails(): Locator {
        return this.page.locator(`//div[@data-name='node-details-panel']//button[@title='Copy src to clipboard']`);
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

    async clickonTipBtn(): Promise<void> {
        await this.tipBtn.click();
    }

    async isTipMenuVisible(): Promise<boolean> {
        await delay(500);
        return await this.genericMenu.isVisible();
    }

    async clickonTipMenuCloseBtn(): Promise<void> {
        await this.tipMenuCloseBtn.click();
    }

    /* Chat functionality */
    async clickOnshowPathBtn(): Promise<void> {
        await this.showPathBtn.click();
    }
    
    async clickAskquestionBtn(): Promise<void> {
        await this.askquestionBtn.click();
    }

    async sendMessage(message: string) {
        await delay(3000); //delay before sending a request to the AI model 
        await waitToBeEnabled(this.askquestionInput);
        await this.askquestionInput.fill(message);
        await this.askquestionBtn.click();
    }

    async clickOnLightBulbBtn(): Promise<void> {
        await this.lightbulbBtn.click();
    }

    async getTextInLastChatElement(): Promise<string>{
        await this.page.waitForSelector('img[alt="Waiting for response"]', { state: 'hidden' });
        await delay(2000); //delay for chat response animation 
        return (await this.lastElementInChat.textContent())!;
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
        await delay(500);
        return await this.notificationError.isVisible();
    }

    async clickOnNotificationErrorCloseBtn(): Promise<void> {
        await this.notificationErrorCloseBtn.click();
    }

    async clickOnQuestionOptionsMenu(): Promise<void> {
        await this.questionOptionsMenu.click();
    }

    async selectAndGetQuestionInOptionsMenu(questionNumber: string): Promise<string> {
        await this.selectQuestionInMenu(questionNumber).click();
        return await this.selectQuestionInMenu(questionNumber).innerHTML();
    }

    async getLastQuestionInChat(): Promise<string> {
        return await this.lastQuestionInChat.innerText();
    }

    /* CodeGraph functionality */
    async selectGraph(graph: string | number): Promise<void> {
        await this.comboBoxbtn.click();
        if(typeof graph === 'number'){
            await this.selectGraphInComboBoxById(graph.toString()).waitFor({ state : 'visible'})
            await this.selectGraphInComboBoxById(graph.toString()).click();
        } else {
            await this.selectGraphInComboBoxByName(graph).waitFor({ state : 'visible'})
            await this.selectGraphInComboBoxByName(graph).click();
        }
        await delay(2000); // graph animation delay
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
        await this.searchBarAutoCompleteOptions.first().waitFor({ state: 'visible' });
        return await this.searchBarAutoCompleteOptions.count();
    }

    async getSearchBarElementsText(): Promise<string[]> {
        return await this.searchBarElements.allTextContents();
    }

    async selectSearchBarOptionBtn(buttonNum: string): Promise<void> {
        await delay(1000);
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

    async clickZoomIn(): Promise<void> {
        await this.zoomInBtn.click();
    }

    async clickZoomOut(): Promise<void> {
        await this.zoomOutBtn.click();
    }

    async clickCenter(): Promise<void> {
        await this.centerBtn.click();
        await delay(2000); //animation delay
    }

    async clickOnRemoveNodeViaElementMenu(): Promise<void> {
        await this.elementMenuButton("Remove").click();
    }

    async nodeClick(x: number, y: number): Promise<void> {
        await this.canvasElement.hover({ position: { x, y } });
        await this.canvasElement.click({ position: { x, y }, button: 'right' });
    }
    
    async selectCodeGraphCheckbox(checkbox: string): Promise<void> {
        await this.codeGraphCheckbox(checkbox).click();
    }

    async clickOnClearGraphBtn(): Promise<void> {
        await this.clearGraphBtn.click();
    }

    async clickOnUnhideNodesBtn(): Promise<void> {
        await this.unhideNodesBtn.click();
    }

    async changeNodePosition(x: number, y: number): Promise<void> {
        const box = (await this.canvasElement.boundingBox())!;
        const targetX = x + 100;
        const targetY = y + 50;
        const absStartX = box.x + x;
        const absStartY = box.y + y;
        const absEndX = box.x + targetX;
        const absEndY = box.y + targetY;
        await this.page.mouse.move(absStartX, absStartY);
        await this.page.mouse.down();
        await this.page.mouse.move(absEndX, absEndY);
        await this.page.mouse.up();
    }

    async isNodeDetailsPanel(): Promise<boolean> {
        return this.nodeDetailsPanel.isVisible();
    }

    async clickOnViewNode(): Promise<void> {
        await this.elementMenuButton("View Node").click();
    }

    async getNodeDetailsHeader(): Promise<string> {
        await this.elementMenuButton("View Node").click();
        const text = await this.nodedetailsPanelHeader.innerHTML();
        return text;
    }

    async clickOnNodeDetailsCloseBtn(): Promise<void>{
        await this.nodedetailsPanelcloseBtn.click();
    }

    async getMetricsPanelInfo(): Promise<{nodes: string, edges: string}> {
        const nodes = await this.canvasMetricsPanel("1").innerHTML();
        const edges = await this.canvasMetricsPanel("2").innerHTML();
        return { nodes, edges }
    }

    async clickOnCopyToClipboardNodePanelDetails(): Promise<string> {
        await this.copyToClipboardNodePanelDetails.click();
        await delay(1000)
        return await this.page.evaluate(() => navigator.clipboard.readText());
    }

    async clickOnCopyToClipboard(): Promise<string> {
        await this.elementMenuButton("Copy src to clipboard").click();
        await delay(1000)
        return await this.page.evaluate(() => navigator.clipboard.readText());
    }

    async getNodedetailsPanelID(): Promise<string> {
        return await this.nodedetailsPanelID.innerHTML();
    }

    async getNodeDetailsPanelElements(): Promise<string[]> {
        await this.elementMenuButton("View Node").click();
        await delay(500)
        const elements = await this.nodedetailsPanelElements.all();
        return Promise.all(elements.map(element => element.innerHTML()));
    }

    async getGraphDetails(): Promise<any> {
        await this.canvasElementBeforeGraphSelection.waitFor({ state: 'detached' });
        await delay(2000)
        await this.page.waitForFunction(() => !!window.graph);
    
        const graphData = await this.page.evaluate(() => {
            return window.graph;
        });
        
        return graphData;
    }

    async transformNodeCoordinates(graphData: any): Promise<any[]> {
        const { canvasLeft, canvasTop, canvasWidth, canvasHeight, transform } = await this.canvasElement.evaluate((canvas: HTMLCanvasElement) => {
            const rect = canvas.getBoundingClientRect();
            const ctx = canvas.getContext('2d');
            const transform = ctx?.getTransform()!; 
            return {
                canvasLeft: rect.left,
                canvasTop: rect.top,
                canvasWidth: rect.width,
                canvasHeight: rect.height,
                transform,
            };
        });

        const screenCoordinates = graphData.elements.nodes.map((node: any) => {
            const adjustedX = node.x * transform.a + transform.e; 
            const adjustedY = node.y * transform.d + transform.f;
            const screenX = canvasLeft + adjustedX - 35;
            const screenY = canvasTop + adjustedY - 190;
    
            return {...node, screenX, screenY,};
        });
    
        return screenCoordinates;
    }
   
    async getCanvasScaling(): Promise<{ scaleX: number; scaleY: number }> {
        const { scaleX, scaleY } = await this.canvasElement.evaluate((canvas: HTMLCanvasElement) => {
            const ctx = canvas.getContext('2d');
            const transform = ctx?.getTransform();
            return {
                scaleX: transform?.a || 1,
                scaleY: transform?.d || 1,
            };
        });
        return { scaleX, scaleY };
    }

}
