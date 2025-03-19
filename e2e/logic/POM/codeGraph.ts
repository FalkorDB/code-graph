import { Download, Locator, Page } from "playwright";
import BasePage from "../../infra/ui/basePage";
import { waitForElementToBeVisible, waitForStableText, waitToBeEnabled } from "../utils";

declare global {
    interface Window {
        graph: any;
    }
}

export default class CodeGraph extends BasePage {

    private isMobile: boolean = false;

    public setMobileState(isMobile: boolean): void {
        this.isMobile = isMobile;
    }

    private get container(): Locator {
        return this.page.locator(this.isMobile ? "#mobile" : "#desktop");
    }

    private get scopedLocator(): (selector: string) => Locator {
        return (selector: string) => this.container.locator(selector);
    }
    
    /* NavBar Locators*/
    private get falkorDBLogo(): Locator {
        return this.scopedLocator("//*[img[@alt='FalkorDB']]")
    }

    private get navBaritem(): (navItem: string) => Locator {
        return (navItem: string) => this.scopedLocator(`//a[p[text() = '${navItem}']]`);
    }

    private get createNewProjectBtn(): Locator {
        return this.page.getByRole('button', { name: 'Create new project' });
    }

    private get createNewProjectDialog(): Locator {
        return this.scopedLocator("//div[@role='dialog']")
    }

    private get tipBtn(): Locator {
        return this.scopedLocator("//button[@title='Tip']")
    }

    private get genericMenu(): Locator {
        return this.page.locator("//div[contains(@role, 'menu')]")
    }

    private get tipMenuCloseBtn(): Locator {
        return this.page.locator("//div[@role='menu']//button[@title='Close']")
    }

    /* CodeGraph Locators*/
    private get comboBoxbtn(): Locator {
        return this.scopedLocator("//button[@role='combobox']")
    }

    private get selectGraphInComboBoxByName(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']//div//span[contains(text(), '${graph}')]`);
    }

    private get selectGraphInComboBoxById(): (graph: string) => Locator {
        return (graph: string) => this.page.locator(`//div[@role='presentation']//div[${graph}]`);
    }

    private get lastElementInChat(): Locator {
        return this.scopedLocator("//main[@data-name='main-chat']/*[last()]/span");
    }

    private get typeUrlInput(): Locator {
        return this.scopedLocator("//div[@role='dialog']/form/input");
    }

    private get createBtnInCreateProjectDialog(): Locator {
        return this.scopedLocator("//div[@role='dialog']/form//following::button//p[contains(text(), 'Create')]")
    }

    private get createProjectWaitDialog(): Locator {
        return this.scopedLocator("//div[@role='dialog']//div//h2[contains(text(), 'THANK YOU FOR A NEW REQUEST')]")
    }

    private get dialogCreatedGraphsList(): (graph: string) => Locator {
        return (graph: string) => this.scopedLocator(`//div[@role='presentation']/div//span[2][contains(text(), '${graph}')]`);
    }

    private get searchBarInput(): Locator {
        return this.scopedLocator("//div[@data-name='search-bar']/input");
    }

    private get searchBarAutoCompleteOptions(): Locator {
        return this.scopedLocator("//div[@data-name='search-bar']/div/button");
    }

    private get searchBarElements(): Locator {
        return this.scopedLocator("//div[@data-name='search-bar']/div/button/div/p[1]");
    }

    private get searchBarOptionBtn(): (buttonNum: string) => Locator {
        return (buttonNum: string) => this.scopedLocator(`//div[@data-name='search-bar']//button[${buttonNum}]`);
    }

    private get searchBarList(): Locator {
        return this.scopedLocator("//div[@data-name='search-bar-list']");
    }

    /* Chat Locators */

    private get showPathBtn(): (selection: string) => Locator {
        return (selection: string) => this.page.locator(`//button[contains(@class, 'Tip')]//p[contains(text(), '${selection}')]`);
    }

    private get askquestionInput(): Locator {
        return this.scopedLocator("//input[contains(@placeholder, 'Ask your question')]");
    }

    private get askquestionBtn(): Locator {
        return this.scopedLocator("//input[contains(@placeholder, 'Ask your question')]/following::button[1]");
    }

    private get lightbulbBtn(): Locator {
        return this.scopedLocator("//button[@data-name='lightbulb']");
    }

    private get lastChatElementButtonCount(): Locator {
        return this.scopedLocator("//main[@data-name='main-chat']/*[last()]/button");
    }

    private get chatContainer(): Locator {
        return this.scopedLocator("//main[@data-name='main-chat']");
    }

    private get previousQuestionLoadingImage(): Locator {
        return this.scopedLocator("//main[@data-name='main-chat']/*[last()-2]//img[@alt='Waiting for response']")
    }

    private get selectInputForShowPath(): (inputNum: string) => Locator {
        return (inputNum: string) => this.scopedLocator(`(//main[@data-name='main-chat']//input)[${inputNum}]`);
    }

    private get locateNodeInLastChatPath(): (node: string) => Locator {
        return (node: string) => this.page.locator(`(//main[@data-name='main-chat']//button//span[contains(text(), ${node})])[last()]`);
    }

    private get selectFirstPathOption(): (inputNum: string) => Locator {
        return (inputNum: string) => this.scopedLocator(`(//main[@data-name='main-chat']//input)[1]/following::div[${inputNum}]//button[1]`);
    }

    private get notificationError(): Locator {
        return this.page.locator("//div[@role='region']//ol//li");
    }

    private get notificationErrorCloseBtn(): Locator {
        return this.page.locator("//div[@role='region']//ol//li/button");
    }

    private get selectQuestionInMenu(): (questionNumber: string) => Locator {
        return (questionNumber: string) => this.page.locator(`//div[contains(@role, 'menu')]/button[${questionNumber}]`);
    }

    private get lastQuestionInChat(): Locator {
        return this.scopedLocator("//main[@data-name='main-chat']/*[last()-1]/p");
    }

    private get responseLoadingImg(): Locator {
        return this.scopedLocator("//img[@alt='Waiting for response']");
    }

    private get waitingForResponseIndicator(): Locator {
        return this.scopedLocator('img[alt="Waiting for response"]');
    }

    /* Canvas Locators*/

    private get canvasElement(): Locator {
        return this.scopedLocator("//canvas");
    }

    private get zoomInBtn(): Locator {
        return this.scopedLocator("//button[@title='Zoom In']");
    }

    private get zoomOutBtn(): Locator {
        return this.scopedLocator("//button[@title='Zoom Out']");
    }

    private get centerBtn(): Locator {
        return this.scopedLocator("//button[@title='Center']");
    }

    private get codeGraphCheckbox(): (checkbox: string) => Locator {
        return (checkbox: string) => this.scopedLocator(`(//button[@role='checkbox'])[${checkbox}]`);
    }

    private get clearGraphBtn(): Locator {
        return this.scopedLocator("//button[p[text()='Reset Graph']]");
    }

    private get unhideNodesBtn(): Locator {
        return this.scopedLocator("//button[p[text()='Unhide Nodes']]");
    }

    private get elementMenuButton(): (buttonID: string) => Locator {
        return (buttonID: string) => this.page.locator(`//button[@title='${buttonID}']`);
    }

    private get nodeDetailsPanel(): Locator {
        return this.scopedLocator("//div[@data-name='node-details-panel']");
    }

    private get elementMenu(): Locator {
        return this.scopedLocator("//div[@id='elementMenu']");
    }
    
    private get nodedetailsPanelHeader(): Locator {
        return this.scopedLocator("//div[@data-name='node-details-panel']/header/p");
    }
    
    private get nodedetailsPanelcloseBtn(): Locator {
        return this.scopedLocator("//div[@data-name='node-details-panel']/header/button");
    }
    private get canvasMetricsPanel(): (itemId: string) => Locator {
        return (itemId: string) => this.scopedLocator(`//div[@data-name='metrics-panel']/p[${itemId}]`);
    }

    private get nodedetailsPanelID(): Locator {
        return this.scopedLocator("//div[@data-name='node-details-panel']/main/div[1]/p[2]");
    }

    private get nodedetailsPanelElements(): Locator {
        return this.scopedLocator("//div[@data-name='node-details-panel']/main/div/p[1]");
    }

    private get canvasElementBeforeGraphSelection(): Locator {
        return this.scopedLocator("//h1[contains(text(), 'Select a repo to show its graph here')]");
    }

    private get copyToClipboardNodePanelDetails(): Locator {
        return this.scopedLocator(`//div[@data-name='node-details-panel']//button[@title='Copy src to clipboard']`);
    }

    private get nodeToolTip(): (node: string) => Locator {
        return (node: string) => this.page.locator(`//div[contains(@class, 'force-graph-container')]/div[contains(text(), '${node}')]`);
    }

    private get downloadImageBtn(): Locator {
        return this.scopedLocator("//button[@title='downloadImage']");
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
        return await this.genericMenu.isVisible();
    }
    
    async clickOnTipMenuCloseBtn(): Promise<void> {
        const isVisible = await waitForElementToBeVisible(this.tipMenuCloseBtn);
        if (!isVisible) throw new Error("'Tip Menu Close' button is not visible!");
        await this.tipMenuCloseBtn.click();
    }
    

    /* Chat functionality */
    async clickOnShowPathBtn(selection: string): Promise<void> {
        await this.showPathBtn(selection).click();
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
        await this.page.mouse.click(10, 10);
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
    
    async selectAndGetQuestionInOptionsMenu(questionNumber: string): Promise<string> {
        const question = this.selectQuestionInMenu(questionNumber);
        await question.click();
        return await question.innerText();
    }
    
    async getLastQuestionInChat(): Promise<string> {
        const isVisible = await waitForElementToBeVisible(this.lastQuestionInChat);
        if (!isVisible) throw new Error("Last question in chat is not visible!");
        return (await this.lastQuestionInChat.innerText()) ?? "";
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
        if (!isVisible) throw new Error("'Remove' button is not visible!");
        await button.click();
    }

    async nodeClick(x: number, y: number): Promise<void> {
        await this.waitForCanvasAnimationToEnd();
        for (let attempt = 1; attempt <= 3; attempt++) {
            await this.canvasElement.hover({ position: { x, y } });
            await this.page.waitForTimeout(500);
            await this.canvasElement.click({ position: { x, y }, button: 'right' });
            if (await this.elementMenu.isVisible()) {
                return;
            }
            await this.page.waitForTimeout(1000);
        }
    
        throw new Error(`Failed to click, elementMenu not visible after multiple attempts.`);
    }
    
    
    async selectCodeGraphCheckbox(checkbox: string): Promise<void> {
        await this.codeGraphCheckbox(checkbox).click();
    }

    async clickOnClearGraphBtn(): Promise<void> {
        await this.page.mouse.click(10, 10);
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
        const edges = await this.canvasMetricsPanel("3").innerHTML();
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
        await this.waitForCanvasAnimationToEnd();
        await this.page.waitForFunction(() => !!window.graph);
    
        const graphData = await this.page.evaluate(() => {
            return window.graph;
        });
        
        return graphData;
    }
    

    async getGraphNodes(): Promise<any[]> {
        await this.waitForCanvasAnimationToEnd();
    
        const graphData = await this.page.evaluate(() => {
            return (window as any).graph;
        });
    
        let transformData: any = null;
        for (let attempt = 0; attempt < 3; attempt++) {
            await this.page.waitForTimeout(1000);
    
            transformData = await this.canvasElement.evaluate((canvas: HTMLCanvasElement) => {
                const rect = canvas.getBoundingClientRect();
                const ctx = canvas.getContext('2d');
                return {
                    left: rect.left,
                    top: rect.top,
                    transform: ctx?.getTransform() || null,
                };
            });
    
            if (transformData.transform) break;
            console.warn(`Attempt ${attempt + 1}: Transform data not available, retrying...`);
        }
    
        if (!transformData?.transform) throw new Error("Canvas transform data not available!");
    
        const { a, e, d, f } = transformData.transform;
        return graphData.elements.nodes.map((node: any) => ({
            ...node,
            screenX: transformData.left + node.x * a + e - 35,
            screenY: transformData.top + node.y * d + f - 190,
        }));
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

    async downloadImage(): Promise<Download> {
        await this.page.waitForLoadState('networkidle');
        const [download] = await Promise.all([
            this.page.waitForEvent('download'),
            this.downloadImageBtn.click(),
        ]);

        return download;
    }

    async rightClickAtCanvasCenter(): Promise<void> {
        const boundingBox = await this.canvasElement.boundingBox();
        if (!boundingBox) throw new Error('Canvas bounding box not found');
        const centerX = boundingBox.x + boundingBox.width / 2;
        const centerY = boundingBox.y + boundingBox.height / 2;
        await this.page.mouse.click(centerX, centerY, { button: 'right' });
    }

    async hoverAtCanvasCenter(): Promise<void> {
        const boundingBox = await this.canvasElement.boundingBox();
        if (!boundingBox) throw new Error('Canvas bounding box not found');
        const centerX = boundingBox.x + boundingBox.width / 2;
        const centerY = boundingBox.y + boundingBox.height / 2;
        await this.page.mouse.move(centerX, centerY);
    }

    async isNodeToolTipVisible(node: string): Promise<boolean> {
        await this.page.waitForTimeout(500);
        return await this.nodeToolTip(node).isVisible();
    }

    async waitForCanvasAnimationToEnd(timeout = 15000, checkInterval = 500): Promise<void> {
        const canvasHandle = await this.canvasElement.elementHandle();
    
        if (!canvasHandle) {
            throw new Error("Canvas element not found!");
        }
    
        await this.page.waitForFunction(
            async ({ canvas, checkInterval, timeout }) => {
                const ctx = canvas.getContext('2d');
                if (!ctx) return false;
    
                const width = canvas.width;
                const height = canvas.height;
    
                let previousData = ctx.getImageData(0, 0, width, height).data;
                const startTime = Date.now();
    
                return new Promise<boolean>((resolve) => {
                    const checkCanvas = () => {
                        if (Date.now() - startTime > timeout) {
                            resolve(true);
                            return;
                        }
    
                        setTimeout(() => {
                            const currentData = ctx.getImageData(0, 0, width, height).data;
                            if (JSON.stringify(previousData) === JSON.stringify(currentData)) {
                                resolve(true);
                            } else {
                                previousData = currentData;
                                checkCanvas();
                            }
                        }, checkInterval);
                    };
                    checkCanvas();
                });
            },
            { 
                canvas: await canvasHandle.evaluateHandle((el) => el as HTMLCanvasElement),
                checkInterval,
                timeout
            },
            { timeout }
        );
    }
}
