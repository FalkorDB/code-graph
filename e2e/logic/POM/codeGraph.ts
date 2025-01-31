import { Locator, Page } from "playwright";
import BasePage from "../../infra/ui/basePage";
import { waitForElementToBeVisible, waitForStableText, waitToBeEnabled } from "../utils";

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

    private get waitingForResponseIndicator(): Locator {
        return this.page.locator('img[alt="Waiting for response"]');
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

    private get elementMenu(): Locator {
        return this.page.locator("//div[@id='elementMenu']");
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
        const isVisible = await waitForElementToBeVisible(this.createNewProjectBtn);
        if (!isVisible) throw new Error("'Create New Project' button is not visible!");
        await this.createNewProjectBtn.click();
    }
    
    async isCreateNewProjectDialog(): Promise<boolean> {
        return await waitForElementToBeVisible(this.createNewProjectDialog);
    }
    
    async clickOnTipBtn(): Promise<void> {
        await this.tipBtn.click();
    }

    async isTipMenuVisible(): Promise<boolean> {
        await this.page.waitForTimeout(500);
        return await waitForElementToBeVisible(this.genericMenu);
    }
    
    async clickOnTipMenuCloseBtn(): Promise<void> {
        const isVisible = await waitForElementToBeVisible(this.tipMenuCloseBtn);
        if (!isVisible) throw new Error("'Tip Menu Close' button is not visible!");
        await this.tipMenuCloseBtn.click();
    }
    

    /* Chat functionality */
    async clickOnShowPathBtn(): Promise<void> {
        await this.showPathBtn.click();
    }
    
    async clickAskQuestionBtn(): Promise<void> {
        const isVisible = await waitForElementToBeVisible(this.askquestionBtn);
        if (!isVisible) throw new Error("'Ask Question' button is not visible!");
        await this.askquestionBtn.click();
    }
    
    async sendMessage(message: string) {
        await waitToBeEnabled(this.askquestionBtn);
        await this.askquestionInput.fill(message);
        await this.askquestionBtn.click();
    }
    
    async clickOnLightBulbBtn(): Promise<void> {
        await this.lightbulbBtn.click();
    }

    async getTextInLastChatElement(): Promise<string>{
        await this.waitingForResponseIndicator.waitFor({ state: 'hidden' });
        return await waitForStableText(this.lastElementInChat);
    }

    async getLastChatElementButtonCount(): Promise<number | null> {
        const isVisible = await waitForElementToBeVisible(this.lastChatElementButtonCount);
        if (!isVisible) return null;
        return await this.lastChatElementButtonCount.count();
    }

    async scrollToTop(): Promise<void> {
        const isVisible = await waitForElementToBeVisible(this.chatContainer);
        if (!isVisible) throw new Error("Chat container is not visible!");
    
        await this.chatContainer.evaluate((chat) => {
            chat.scrollTop = 0;
        });
    }
    
    async getScrollMetrics() {
        const isVisible = await waitForElementToBeVisible(this.chatContainer);
        if (!isVisible) throw new Error("Chat container is not visible!");
    
        return await this.chatContainer.evaluate((el) => ({
            scrollTop: el.scrollTop,
            scrollHeight: el.scrollHeight,
            clientHeight: el.clientHeight
        }));
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
        const nodeLocator = this.locateNodeInLastChatPath(node);
        return await waitForElementToBeVisible(nodeLocator);
    }

    async isNotificationError(): Promise<boolean> {
        await this.page.waitForTimeout(500);
        return await this.notificationError.isVisible();
    }

    async clickOnNotificationErrorCloseBtn(): Promise<void> {
        const isVisible = await waitForElementToBeVisible(this.notificationErrorCloseBtn);
        if (!isVisible) throw new Error("Notification error close button is not visible!");
        await this.notificationErrorCloseBtn.click();
    }
    
    async clickOnQuestionOptionsMenu(): Promise<void> {
        const isVisible = await waitForElementToBeVisible(this.questionOptionsMenu);
        if (!isVisible) throw new Error("Question options menu is not visible!");
        await this.questionOptionsMenu.click();
    }
    
    async selectAndGetQuestionInOptionsMenu(questionNumber: string): Promise<string> {
        const question = this.selectQuestionInMenu(questionNumber);
        const isVisible = await waitForElementToBeVisible(question);
        if (!isVisible) throw new Error(`Question ${questionNumber} in menu is not visible!`);
        
        await question.click();
        return await question.innerHTML();
    }
    
    async getLastQuestionInChat(): Promise<string> {
        const isVisible = await waitForElementToBeVisible(this.lastQuestionInChat);
        if (!isVisible) throw new Error("Last question in chat is not visible!");
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
        await this.page.waitForTimeout(2000); // graph animation delay
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
        const button = this.searchBarOptionBtn(buttonNum);
        await button.waitFor({ state : "visible"})
        await button.click();
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
        await this.page.waitForTimeout(2000); //animation delay
    }

    async clickOnRemoveNodeViaElementMenu(): Promise<void> {
        const button = this.elementMenuButton("Remove"); 
        const isVisible = await waitForElementToBeVisible(button);
        if (!isVisible) throw new Error("'View Node' button is not visible!");
        await button.click();
    }

    async nodeClick(x: number, y: number): Promise<void> {
        await this.canvasElement.hover({ position: { x, y } });
        await this.page.waitForTimeout(500); // Allow hover to take effect
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
        await this.page.waitForTimeout(500);
        return this.nodeDetailsPanel.isVisible();
    }

    async clickOnViewNode(): Promise<void> {
        const button = this.elementMenuButton("View Node");
        const isButtonVisible = await waitForElementToBeVisible(button);
        if (!isButtonVisible) throw new Error("'View Node' button is not visible!");
        await button.click();
    }

    async getNodeDetailsHeader(): Promise<string> {
        const isMenuVisible = await waitForElementToBeVisible(this.elementMenu);
        if (!isMenuVisible) throw new Error("Element menu did not appear!");

        await this.clickOnViewNode();

        const isHeaderVisible = await waitForElementToBeVisible(this.nodedetailsPanelHeader);
        if (!isHeaderVisible) throw new Error("Node details panel header did not appear!");

        return this.nodedetailsPanelHeader.innerHTML();
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
        const isButtonVisible = await waitForElementToBeVisible(this.copyToClipboardNodePanelDetails);
        if (!isButtonVisible) throw new Error("'copy to clipboard button is not visible!");
        await this.copyToClipboardNodePanelDetails.click();
        return await this.page.evaluate(() => navigator.clipboard.readText());
    }

    async clickOnCopyToClipboard(): Promise<string> {
        const button = this.elementMenuButton("Copy src to clipboard"); 
        const isVisible = await waitForElementToBeVisible(button);
        if (!isVisible) throw new Error("View Node button is not visible!");
        await button.click(); 
        return await this.page.evaluate(() => navigator.clipboard.readText());
    }

    async getNodedetailsPanelID(): Promise<string> {
        return await this.nodedetailsPanelID.innerHTML();
    }

    async getNodeDetailsPanelElements(): Promise<string[]> {
        const button = this.elementMenuButton("View Node");
        const isVisible = await waitForElementToBeVisible(button);
        if (!isVisible) throw new Error("View Node button is not visible!");
        await button.click();

        const isPanelVisible = await waitForElementToBeVisible(this.nodedetailsPanelElements.first());
        if (!isPanelVisible) throw new Error("Node details panel did not appear!");

        const elements = await this.nodedetailsPanelElements.all();
        return Promise.all(elements.map(element => element.innerHTML()));
    }

    async getGraphDetails(): Promise<any> {
        await this.canvasElementBeforeGraphSelection.waitFor({ state: 'detached' });
        await this.page.waitForTimeout(2000); //canvas animation
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
